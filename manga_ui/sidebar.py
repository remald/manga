from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QCheckBox,
    QFontComboBox, QSpinBox,
)

from .i18n import t


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

        self.enabled_checkbox = QCheckBox(t("enabled_checkbox"))
        self.enabled_checkbox.toggled.connect(self._on_enabled_toggled)

        self.uppercase_checkbox = QCheckBox(t("uppercase_checkbox"))
        self.uppercase_checkbox.toggled.connect(self._on_uppercase_toggled)

        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._on_font_changed)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 200)
        self.size_spin.valueChanged.connect(self._on_size_changed)

        self.font_label = QLabel(t("font_label"))
        self.size_label = QLabel(t("size_label"))
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_label)
        font_row.addWidget(self.font_combo, 1)
        font_row.addWidget(self.size_label)
        font_row.addWidget(self.size_spin)

        self.translation_edit = QPlainTextEdit()
        self.translation_edit.textChanged.connect(self._on_text_changed)

        self.original_label = QLabel(t("original_label"))
        self.translation_label = QLabel(t("translation_label"))
        layout.addWidget(self.original_label)
        layout.addWidget(self.source_view)
        layout.addWidget(self.enabled_checkbox)
        layout.addWidget(self.uppercase_checkbox)
        layout.addLayout(font_row)
        layout.addWidget(self.translation_label)
        layout.addWidget(self.translation_edit)
        layout.addStretch()

        self.setEnabled(False)

    def retranslate_ui(self):
        self.enabled_checkbox.setText(t("enabled_checkbox"))
        self.uppercase_checkbox.setText(t("uppercase_checkbox"))
        self.font_label.setText(t("font_label"))
        self.size_label.setText(t("size_label"))
        self.original_label.setText(t("original_label"))
        self.translation_label.setText(t("translation_label"))

    def set_region(self, item):
        self._updating = True
        self._current_item = item
        if item is None:
            self.setEnabled(False)
            self.source_view.setPlainText("")
            self.translation_edit.setPlainText("")
            self.enabled_checkbox.setChecked(True)
            self.uppercase_checkbox.setChecked(True)
        else:
            self.setEnabled(True)
            self.source_view.setPlainText(item.source_text)
            self.translation_edit.setPlainText(item.translated_text)
            self.enabled_checkbox.setChecked(item.translation_enabled)
            self.uppercase_checkbox.setChecked(item.uppercase)
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

    def _on_uppercase_toggled(self, checked):
        if self._updating or self._current_item is None:
            return
        self._current_item.set_uppercase(checked)
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

    def sync_font_size(self, item):
        """Reflect an auto-fitted size in the spinbox without treating it
        as a manual user choice."""
        if item is not self._current_item:
            return
        self._updating = True
        self.size_spin.setValue(item.font_size)
        self._updating = False
