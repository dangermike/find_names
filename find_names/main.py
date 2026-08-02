#!/usr/bin/env python
import argparse
import json
import logging
import re
from collections.abc import Generator, Iterable
import sys
from typing import TypeVar
import yaml

from case_insensitive_dict import CaseInsensitiveDict
from docx import Document
from docx.document import Document as DocumentObject
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    Pipeline,
    PreTrainedModel,
    PreTrainedTokenizer,
    pipeline,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)

bad_chars = re.compile(r'["“—\-‘’. ]')


def uniq[T](src: Iterable[T]) -> Generator[T]:
    """
    uniq returns all unique items in the source. Like the `uniq` command, this
    only considers consecutive unique values, so actual uniqueness in the output
    depends on the order of the input.
    """
    prev: T | None = None
    first = True
    for item in src:
        match = prev == item
        prev = item

        if first or not match:
            first = False
            yield item


class Ref:
    """
    Ref represents a referenced name in the source
    """

    chapter: int = -1
    paragraph: int = -1
    start: int = -1
    end: int = -1
    entity: str = ""
    name: str = ""

    def is_empty(self) -> bool:
        return self.start == -1

    def __repr__(self) -> str:
        return f'Reference(ch: {self.chapter}, para: {self.paragraph}, start: {self.start}, end: {self.end}, entity: "{self.entity}", name: "{self.name}")'


class Processor:
    """
    Processor uses the provided pipeline and a source document to emit Refs.
    Note that chapter matching is done by comparing whole paragraphs to the form
    "Chapter XXX" where XXX is a number from 1-99 in spelled-out English or
    numeral, with or without dashes, such as "Chapter Thirty-Nine".
    """

    def __init__(self, nlp: Pipeline):
        self.nlp: Pipeline = nlp

        chdict: dict[str, int] = {}
        numstrs = [
            "One",
            "Two",
            "Three",
            "Four",
            "Five",
            "Six",
            "Seven",
            "Eight",
            "Nine",
        ]
        for i, n in enumerate(numstrs):
            chdict[f"Chapter {n}"] = i + 1
            chdict[f"Chapter {i + 1}"] = i + 1

        for i, n in enumerate(
            [
                "Ten",
                "Eleven",
                "Twelve",
                "Thirteen",
                "Fourteen",
                "Fifteen",
                "Sixteen",
                "Seventeen",
                "Eighteen",
                "Ninenteen",
            ]
        ):
            chdict[f"Chapter {n}"] = i + 10
            chdict[f"Chapter {i + 10}"] = i + 10

        for i, pre in enumerate(
            [
                "Twenty",
                "Thirty",
                "Forty",
                "Fifty",
                "Sixty",
                "Seventy",
                "Eighty",
                "Ninety",
            ]
        ):
            tens = (i * 10) + 20
            chdict[f"Chapter {pre}"] = tens
            chdict[f"Chapter {tens}"] = tens
            for j, n in enumerate(numstrs):
                chnum = tens + j + 1
                chdict[f"Chapter {pre} {n}"] = chnum
                chdict[f"Chapter {pre}-{n}"] = chnum
                chdict[f"Chapter {chnum}"] = chnum
        self.chapterMap = CaseInsensitiveDict[str, int](chdict)

    def process_doc(self, document: DocumentObject) -> Generator[Ref]:
        """
        process_doc uses the provided pipeline and a source document to emit Refs
        """
        chnum = 0
        pnum = 0
        for para in document.paragraphs:
            pnum += 1
            txt = para.text

            logger.debug(f"PARA c{chnum}/p{pnum}: {txt}")

            # Is this a chapter marker?
            ch = self.chapterMap.get(txt.lower())
            if ch is not None:
                logger.info(f"CHAPTER: {ch}")
                chnum = ch
                pnum = 0
                continue

            ner_results = self.nlp(txt)
            # print(txt)

            if ner_results is None:
                continue

            ref = Ref()

            for r in ner_results:
                if r is None:
                    continue

                entity_class, entity_type = str(r["entity"]).split("-")
                start, end = int(r["start"]), int(r["end"])

                if ref.is_empty():
                    logger.debug(f"ENTITY c{chnum}/p{pnum}/i{r['index']}: NEW {r}")
                    ref.start = start
                    ref.end = end
                    ref.chapter = chnum
                    ref.paragraph = pnum
                    ref.entity = entity_type
                elif start == ref.end or (entity_class == "I" and start - 1 == ref.end):
                    logger.debug(f"ENTITY c{chnum}/p{pnum}/i{r['index']}: CON {r}")
                    ref.end = end
                else:
                    ref.name = txt[ref.start : ref.end]
                    logger.debug(f"YIELD {ref}")
                    yield ref
                    logger.debug(f"ENTITY c{chnum}/p{pnum}/i{r['index']}: NEW {r}")
                    ref = Ref()
                    ref.start = start
                    ref.end = end
                    ref.chapter = chnum
                    ref.paragraph = pnum
                    ref.entity = entity_type

            if not ref.is_empty():
                ref.name = txt[ref.start : ref.end]
                logger.debug(f"YIELD {ref}")
                yield ref


def normalize(src: str) -> str:
    n = bad_chars.sub("", src.lower())
    if n.startswith(("The ", "the ")):
        n = n[4:] + ", " + n[:3]
    return n


def emit_oneline(results: dict[str, list[Ref]], all: bool = False):
    for v in results.values():
        entz = "|".join(sorted({r.entity for r in v}))
        if all:
            refz = ", ".join(f"{r.chapter}:{r.paragraph}:{r.start}" for r in v)
        else:
            refz = ", ".join(uniq(f"{r.chapter}:{r.paragraph}" for r in v))
        print(f"{v[0].name}::{entz}: {refz}")


def to_dict(
    results: dict[str, list[Ref]], all: bool = False
) -> dict[str, list[dict[str, int]]]:
    out = {}
    for v in results.values():
        if all:
            refz = [
                {"chapter": r.chapter, "paragraph": r.paragraph, "start": r.start}
                for r in v
            ]
        else:
            refz = list(
                uniq([{"chapter": r.chapter, "paragraph": r.paragraph} for r in v])
            )
        out[v[0].name] = {
            "aliases": list(uniq(sorted({r.name for r in v}))),
            "types": sorted({r.entity for r in v}),
            "references": refz,
        }
    return out


def emit_json(results: dict[str, list[Ref]], all: bool = False):
    print(json.dumps(to_dict(results, all)))


def emit_yaml(results: dict[str, list[Ref]], all: bool = False):
    yaml.dump(to_dict(results, all), sys.stdout)


def main():
    parser = argparse.ArgumentParser(
        prog="find_names",
        description="finds names in DOCX files",
        epilog="output to stdout",
    )

    parser.add_argument("filenames", nargs="*")
    parser.add_argument(
        "--format",
        help="shape of the output",
        default="oneline",
        choices=["oneline", "json", "yaml"],
    )
    parser.add_argument(
        "--all",
        help="include multiple refs from the same paragraph",
        action="store_true",
    )
    parser.add_argument(
        "-q", "--quiet", help="reduce log detail", action="count", default=0
    )
    parser.add_argument(
        "-v", "--verbose", help="increase log detail", action="count", default=0
    )

    args = parser.parse_args()

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    lvl = logging.INFO
    if args.quiet == 1:
        lvl = logging.WARNING
    elif args.quiet == 2:
        lvl = logging.ERROR
    elif args.quiet > 2:
        lvl = logging.FATAL
    elif args.verbose == 1:
        lvl = logging.DEBUG
    elif args.verbose == 2:
        lvl = logging.DEBUG
        logging.getLogger("httpx").setLevel(logging.INFO)
        logging.getLogger("httpcore").setLevel(logging.INFO)
    elif args.verbose > 2:
        lvl = logging.DEBUG
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)

    logging.basicConfig(level=lvl)

    # Prepare the pipeline, create Processor with pipeline
    tokenizer: PreTrainedTokenizer = AutoTokenizer.from_pretrained(
        "dslim/distilbert-NER"
    )
    model: PreTrainedModel = AutoModelForTokenClassification.from_pretrained(
        "dslim/distilbert-NER"
    )
    nlp: Pipeline = pipeline(task="ner", model=model, tokenizer=tokenizer)
    proc = Processor(nlp)

    # Gather all the names as a dictionary of normalized name -> Ref(s)
    results: dict[str, list[Ref]] = {}

    for p in args.filenames:
        logger.info(f"opening file: {p}")
        document = Document(p)
        for ref in proc.process_doc(document):
            n = normalize(ref.name)
            arr = results.get(n)
            if arr is None:
                results[n] = [ref]
            else:
                results[n].append(ref)

    # Ordered by name, emit distinct chapter:paragraph pairs. Note that we are
    # using the first instance rather than the normalized name used in
    # collecting the Refs
    results = dict(sorted(results.items()))
    if args.format == "json":
        emit_json(results)
    elif args.format == "yaml":
        emit_yaml(results)
    else:
        emit_oneline(results, args.all)
