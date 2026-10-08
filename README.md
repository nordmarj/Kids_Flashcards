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

To build one language only, use `--lang sv` or `--lang en`. That writes just
that language's word deck plus `build/maths_sv.apkg` or `build/maths_en.apkg`,
whose shapes are in that language only.

## Licences

The code is MIT (see [LICENSE](LICENSE)). The decks are released under
CC BY-NC-SA 4.0, because they bundle ARASAAC pictograms and CC BY-SA
recordings; every media file's source and licence is listed in
[media/sources.csv](media/sources.csv) and [ATTRIBUTION.md](ATTRIBUTION.md).
