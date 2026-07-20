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
        print("Не экспортированы страницы:")
        for line in errors:
            print(f"  {line}")
        sys.exit(1)


def main():
    from manga_ui.main_window import SOURCE_LANGUAGES, TARGET_LANGUAGES

    parser = argparse.ArgumentParser(
        description="Manga Translator: без аргументов открывает GUI, "
        "с --batch переводит папку страниц без интерфейса."
    )
    parser.add_argument(
        "--batch", nargs=2, metavar=("INPUT_DIR", "OUTPUT_DIR"),
        help="перевести все страницы из INPUT_DIR и сохранить в OUTPUT_DIR",
    )
    parser.add_argument(
        "--source-lang", default="Japanese",
        choices=sorted(set(SOURCE_LANGUAGES.values())),
        help="язык оригинала (по умолчанию Japanese)",
    )
    parser.add_argument(
        "--target-lang", default="Russian",
        choices=sorted(set(TARGET_LANGUAGES.values())),
        help="язык перевода (по умолчанию Russian)",
    )
    args = parser.parse_args()
    if args.batch:
        run_batch(args.batch[0], args.batch[1], args.source_lang, args.target_lang)
    else:
        run_gui()


if __name__ == "__main__":
    main()
