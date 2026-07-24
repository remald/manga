import argparse
import os
import sys


def run_gui():
    from PySide6.QtWidgets import QApplication

    from manga_ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def run_batch(input_dir, output_dir, source_lang, target_lang):
    # rendering needs Qt fonts but no window: run off-screen (works over SSH)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from manga_ui.batch import translate_folder

    app = QGuiApplication([])
    errors = translate_folder(input_dir, output_dir, source_lang, target_lang)
    if errors:
        print("Pages not exported:")
        for line in errors:
            print(f"  {line}")
        sys.exit(1)


def main():
    from manga_ui.main_window import SOURCE_LANGS, TARGET_LANGS

    parser = argparse.ArgumentParser(
        description="Manga Translator: launches the GUI with no arguments, "
        "translates a folder of pages headlessly with --batch."
    )
    parser.add_argument(
        "--batch", nargs=2, metavar=("INPUT_DIR", "OUTPUT_DIR"),
        help="translate every page in INPUT_DIR and save into OUTPUT_DIR",
    )
    parser.add_argument(
        "--source-lang", default="Japanese",
        choices=sorted(SOURCE_LANGS),
        help="source language (default: Japanese)",
    )
    parser.add_argument(
        "--target-lang", default="Russian",
        choices=sorted(TARGET_LANGS),
        help="target language (default: Russian)",
    )
    args = parser.parse_args()
    if args.batch:
        run_batch(args.batch[0], args.batch[1], args.source_lang, args.target_lang)
    else:
        run_gui()


if __name__ == "__main__":
    main()
