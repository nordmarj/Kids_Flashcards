# Kids_Flashcards

Source data and build scripts for [Anki](https://apps.ankiweb.net/) flashcard
decks for young children: picture → word cards in Swedish, English, German,
Swahili, Spanish and French, flags and maps (geography), plus arithmetic and shapes. See [CLAUDE.md](CLAUDE.md) for how the project works.

## Build

```sh
pip install -r requirements.txt
python3 scripts/build_decks.py
```

This writes one word deck per language (`build/svenska.apkg` with
`Svenska::Ord::…`, `build/english.apkg` with `English::Words::…`, and
`deutsch`, `kiswahili`, `espanol`, `francais`), one geography deck per
language (`build/geography_sv.apkg` with `Geografi::Flaggor` and
`Geografi::Kartor`, `build/geography_en.apkg` with `Geography::Flags` and
`Geography::Maps`, and so on) and `build/maths.apkg`
(`Maths::…`, with the shapes in every language). Import them into Anki; re-importing an updated deck keeps the
child's progress.

To build only some languages, list them: `--lang sv` or `--lang sv en`. That
writes just those languages' word and geography decks, plus a maths deck whose shapes are in
those languages only, named after them (`build/maths_sv.apkg`). The languages
are defined in `LANGUAGES` in `scripts/word_decks.py`.

The prebuilt maths deck published with each release can't come in every
combination of languages, so it is the Swedish and English one:
`python3 scripts/build_decks.py --lang sv en` (`build/maths_sv_en.apkg`).

## Releases

To publish the decks, run the **Release decks** workflow from the Actions tab
with a new tag (`v0.2.0`). It builds every deck from `main` and attaches them
to a draft release with the notes in `.github/release-notes.md`; review the
draft under Releases and press Publish.

## Licences

The code is MIT (see [LICENSE](LICENSE)). The decks are released under
CC BY-NC-SA 4.0, because they bundle ARASAAC pictograms and CC BY-SA
recordings; every media file's source and licence is listed in
[media/sources.csv](media/sources.csv) and [ATTRIBUTION.md](ATTRIBUTION.md).
