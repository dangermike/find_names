# find_names

This is a very specific tool to solve a very specific problem: Generating an index of proper nouns in a book written in Microsoft Word (.DOCX) format.

While this will run faster with a GPU, the model was chosen because it is reasonable to run on CPU-only machines. This was developed on an Apple M1 Max, which was able to process a novel-length book in ~45 seconds.

## Methodology

Uses the [distilbert-NER](https://huggingface.co/dslim/distilbert-NER) model (a distilled version of the [bert-base-NER](https://huggingface.co/dslim/bert-base-NER) model) for Named Entity Recognition. The model is specifically trained on English. Results on non-English text are not reliable. The model is applied on a per-paragraph basis on documents read using the [python-docx](https://github.com/python-openxml/python-docx) package.

The model results are entities with a type, location, value, etc. These are potentially incomplete. This script will combine incomplete entities into into `Ref` objects, which contain name and location information.

The name in `Ref` objects are grouped together by normalized name (lowercase, removed special characters, `The` moved to the end), which is what gets returned via stdout.

### Chapter identification

The NER model does not identify chapters. This tool does this is a hacky way. If an entire paragraph is `Chapter <num>` where `<num>` is a number from 1-99, the text of a number from 1-99 (e.g. `Thirty Seven`) or a dash-separated number from 1-99 (e.g. `Ninety-Three`), that is considered a chapter. When encountered, the chapter number is extracted and the paragraph number is extracted.

### Paragraph vs. page numbers

The DOCX format breaks the document into *paragraphs*. Paragraphs are further broken down into *runs*, which are small sets of words. Page numbers are more complicated because we would need to count page breaks where we are. If we want to know what page a word is on, we need to operate at the level of *runs*. However, the NER model needs context to get the right answers, which means that we want to feed it *paragraphs*. The right thing to do would be to map page breaks to offsets in paragraphs, but I haven't done that.

## How to run

This was built in Python using [poetry](https://python-poetry.org/) for package and environment management. Install poetry and run with `poetry run find_names`.  The first time you run it, the model will be downloaded from [Hugging Face](https://huggingface.co/), which will take a few minutes.

```plaintext
usage: find_names [-h] [-q] [-v] [filenames ...]

finds names in DOCX files

positional arguments:
  filenames

options:
  -h, --help     show this help message and exit
  -q, --quiet
  -v, --verbose

output to stdout
```

In `verbose` mode (`-v`), the log will contain the paragraph text, the found entities, and the `Ref`s. `-vv` includes INFO logs from the model fetch, `-vvv` includes DEBUG logs.

The specified files are processed in the order given, but the output combines results from all files in alphabetical order.

Output is sent to stdout. It is recommended that output be piped to a file, using standard [redirection](https://www.gnu.org/software/bash/manual/html_node/Redirections.html). I tend to run it with my files in a temporary directory using the following command line:

```bash
poetry run find_names -v tmp/*.docx > tmp/out.txt 2>tmp/log.txt
```

## Output format

The format is `{name}::{type}: {chapter}:{paragraph}`. The one-line format was chosen specifically to make filtering using [grep](https://www.man7.org/linux/man-pages/man1/grep.1.html) (or [ripgrep](https://github.com/BurntSushi/ripgrep)) possible. For the sake of brevity, instances within a single paragraph are only emitted once.

```plaintext
Bell::MISC: 33:168
Bengay::MISC|PER: 10:66, 17:36
Benjamin Franklin::PER: 3:15
Benjamins::MISC: 26:11
Benny Goodman::PER: 23:21
Berklee::LOC|PER: 28:72, 28:73
```

In the example, `Bengay` was found as both a miscellaneous entity (MISC) and a person (PER). As noted above, the names are normalized for grouping, which means that there can be multiple representations of any name. The first one is chosen as it appears in the text. That means that it may start with a smart quote or other special character.

`Bengay` was also found at multiple locations in the text, in chapter 10, paragraph 66 as well as in chapter 17, paragraph 36.

### types

These are defined in the [model documentation](https://huggingface.co/dslim/distilbert-NER#training-data)

| Abbreviation | Description          |
| ------------ | -------------------- |
| MISC         | Miscellaneous entity |
| PER          | Person’s name        |
| ORG          | organization         |
| LOC          | Location             |

## Developer's note

While I do write Python occasionally, it is not what I normally do. Be gentle.

