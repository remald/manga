from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QCheckBox,
    QFontComboBox, QSpinBox,
)


class RegionEditorPanel(QWidget):
    """Shows/edits the currently selected text region: original text (read-only),
    translation toggle, and the editable translated text."""

    region_updated = Signal()

    def __init__(self):
        super().__init__()
        self._current_item = None
        self._updating = False

        layout = QVBoxLayout(self)

        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setMaximumHeight(100)

        self.enabled_checkbox = QCheckBox("Перевод включен для этого фрагмента")
        self.enabled_checkbox.toggled.connect(self._on_enabled_toggled)

        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._on_font_changed)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.valueChanged.connect(self._on_size_changed)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Шрифт:"))
        font_row.addWidget(self.font_combo, 1)
        font_row.addWidget(QLabel("Размер:"))
        font_row.addWidget(self.size_spin)

        self.translation_edit = QPlainTextEdit()
        self.translation_edit.textChanged.connect(self._on_text_changed)

        layout.addWidget(QLabel("Оригинал:"))
        layout.addWidget(self.source_view)
        layout.addWidget(self.enabled_checkbox)
        layout.addLayout(font_row)
        layout.addWidget(QLabel("Перевод:"))
        layout.addWidget(self.translation_edit)
        layout.addStretch()

        self.setEnabled(False)

    def set_region(self, item):
        self._updating = True
        self._current_item = item
        if item is None:
            self.setEnabled(False)
            self.source_view.setPlainText("")
            self.translation_edit.setPlainText("")
            self.enabled_checkbox.setChecked(True)
        else:
            self.setEnabled(True)
            self.source_view.setPlainText(item.source_text)
            self.translation_edit.setPlainText(item.translated_text)
            self.enabled_checkbox.setChecked(item.translation_enabled)
            self.font_combo.setCurrentFont(QFont(item.font_family))
            self.size_spin.setValue(item.font_size)
        self._updating = False

    def _on_text_changed(self):
        if self._updating or self._current_item is None:
            return
        self._current_item.set_translated_text(self.translation_edit.toPlainText())
        self.region_updated.emit()

    def _on_enabled_toggled(self, checked):
        if self._updating or self._current_item is None:
            return
        self._current_item.set_enabled_state(checked)
        self.region_updated.emit()

    def _on_font_changed(self, font: QFont):
        if self._updating or self._current_item is None:
            return
        self._current_item.set_font_family(font.family())
        self.region_updated.emit()

    def _on_size_changed(self, size: int):
        if self._updating or self._current_item is None:
            return
        self._current_item.set_font_size(size)
        self.region_updated.emit()
