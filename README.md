# Kids_Flashcards

Source data and build scripts for [Anki](https://apps.ankiweb.net/) flashcard
decks for young children: picture → word cards in Swedish and English, plus
arithmetic and shapes. See [CLAUDE.md](CLAUDE.md) for how the project works.

## Build

```sh
pip install -r requirements.txt
python3 scripts/build_decks.py
```

This writes `build/svenska.apkg` (`Svenska::Ord::…`), `build/english.apkg`
(`English::Words::…`) and `build/maths.apkg` (`Maths::…`, with the shapes in
both languages). Import them into Anki; re-importing an updated deck keeps the
child's progress.

To build only some languages, list them: `--lang sv` or `--lang sv en`. That
writes just those languages' word decks, plus a maths deck whose shapes are in
those languages only, named after them (`build/maths_sv.apkg`). The languages
are defined in `LANGUAGES` in `scripts/word_decks.py`.

## Licences

The code is MIT (see [LICENSE](LICENSE)). The decks are released under
CC BY-NC-SA 4.0, because they bundle ARASAAC pictograms and CC BY-SA
recordings; every media file's source and licence is listed in
[media/sources.csv](media/sources.csv) and [ATTRIBUTION.md](ATTRIBUTION.md).
