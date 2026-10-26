"""Embedded contact tower map dialog for the desktop GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
# Mapping is optional: missing native WebEngine libraries must not prevent
# authentication, record analysis or reporting from starting.
try:
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except (ImportError, OSError):
    QWebEngineSettings = None
    QWebEngineView = None
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ContactMapDialog(QDialog):
    """Display one generated CDR contact tower map."""

    def __init__(
        self,
        map_path: str | Path,
        parent: QWidget | None = None,
        *,
        window_title: str = "CDR Contact Tower Map",
        heading: str = "Contact Tower Map",
        caution: str = (
            "Markers represent the target handset's serving tower, "
            "not the contact person's exact location."
        ),
    ) -> None:
        super().__init__(
            parent
        )

        self._map_path = Path(
            map_path
        ).expanduser().resolve(
            strict=False
        )
        self._window_title = str(
            window_title
        )
        self._heading = str(
            heading
        )
        self._caution = str(
            caution
        )

        self.setObjectName(
            "contactMapDialog"
        )
        self.setWindowTitle(
            self._window_title
        )
        self.setWindowModality(
            Qt.WindowModality.ApplicationModal
        )
        self.setMinimumSize(
            980,
            680,
        )
        self.resize(
            1280,
            820,
        )

        if QWebEngineView is None:
            self._view = QLabel(
                "Embedded map preview is unavailable on this system. "
                "Use Open in Browser to view the generated map.",
                self,
            )
            self._view.setWordWrap(True)
        else:
            self._view = QWebEngineView(self)
            self._view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                True,
            )

        self._build_layout()
        self._load_map()

    @property
    def map_path(
        self,
    ) -> Path:
        """Return the local map path."""

        return self._map_path

    def _build_layout(
        self,
    ) -> None:
        layout = QVBoxLayout(
            self
        )
        layout.setContentsMargins(
            14,
            14,
            14,
            14,
        )
        layout.setSpacing(
            10
        )

        heading_row = QHBoxLayout()
        heading = QLabel(
            self._heading
        )
        heading.setObjectName(
            "cardHeading"
        )

        open_external = QPushButton(
            "Open in Browser"
        )
        open_external.setObjectName(
            "secondaryButton"
        )
        open_external.clicked.connect(
            self._open_external
        )

        close_button = QPushButton(
            "Close Map"
        )
        close_button.setObjectName(
            "secondaryButton"
        )
        close_button.clicked.connect(
            self.accept
        )

        heading_row.addWidget(
            heading
        )
        heading_row.addStretch()
        heading_row.addWidget(
            open_external
        )
        heading_row.addWidget(
            close_button
        )

        caution = QLabel(
            self._caution
        )
        caution.setObjectName(
            "cardText"
        )
        caution.setWordWrap(
            True
        )

        layout.addLayout(
            heading_row
        )
        layout.addWidget(
            caution
        )
        layout.addWidget(
            self._view,
            stretch=1,
        )

    def _load_map(
        self,
    ) -> None:
        if not self._map_path.is_file():
            QMessageBox.warning(
                self,
                "Map Not Found",
                f"The contact map file is not available:\n{self._map_path}",
            )
            return

        if QWebEngineView is None:
            return

        from gui.utils.local_preview import preview_url
        self._view.setUrl(QUrl(preview_url(self._map_path)))

    def _open_external(
        self,
    ) -> None:
        if not self._map_path.is_file():
            QMessageBox.warning(
                self,
                "Map Not Found",
                f"The contact map file is not available:\n{self._map_path}",
            )
            return

        try:
            from gui.utils.local_preview import open_preview
            open_preview(self._map_path)
        except Exception as error:
            QMessageBox.warning(self, "Open Contact Map", str(error))
