#main_window.py
"""Main desktop window for the application."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui.pages.case_details_page import CaseDetailsPage
from gui.pages.case_reports_page import CaseReportsPage
from gui.pages.cdr_page import CdrPage
from gui.pages.imei_page import ImeiPage
from gui.pages.ipdr_page import IpdrPage
from gui.pages.lookup_page import LookupPage
from gui.pages.tower_dump_page import TowerDumpPage


@dataclass(frozen=True)
class NavigationItem:
    """Describe one investigator-facing GUI module."""

    key: str
    title: str
    description: str


NAVIGATION_ITEMS = (
    NavigationItem(
        key="cdr",
        title="CDR Analysis",
        description=(
            "Review a single CDR or compare multiple CDR files."
        ),
    ),
    NavigationItem(
        key="tower_dump",
        title="Tower Dump Analysis",
        description=(
            "Analyze tower CDR, GPRS and IPDR dump evidence."
        ),
    ),
    NavigationItem(
        key="ipdr",
        title="IPDR Analysis",
        description=(
            "Review subscriber IPDR and network session evidence."
        ),
    ),
    NavigationItem(
        key="imei",
        title="IMEI / Device Analysis",
        description=(
            "Analyze device identifiers across telecom evidence."
        ),
    ),
    NavigationItem(
        key="lookup",
        title="Lookup Services",
        description=(
            "Search SDR subscriber and CGI tower master data."
        ),
    ),
    NavigationItem(
        key="case_details",
        title="Case Details",
        description=(
            "View active case identity and evidence information."
        ),
    ),
    NavigationItem(
        key="case_reports",
        title="View Case Reports",
        description=(
            "Open investigation reports created for the active case."
        ),
    ),
)


class MainWindow(QMainWindow):
    """Provide the primary investigator workspace window."""

    def __init__(
        self,
    ) -> None:
        super().__init__()

        self.setObjectName(
            "mainWindow"
        )
        self.setWindowTitle(
            "Telecom Forensics Analysis Suite"
        )
        self.setMinimumSize(
            1120,
            700,
        )
        self.resize(
            1380,
            840,
        )

        self._navigation_buttons: list[
            QPushButton
        ] = []

        self._button_group = QButtonGroup(
            self
        )
        self._button_group.setExclusive(
            True
        )

        self._page_title = QLabel()
        self._page_title.setObjectName(
            "pageTitle"
        )

        self._page_subtitle = QLabel()
        self._page_subtitle.setObjectName(
            "pageSubtitle"
        )
        self._page_subtitle.setWordWrap(
            True
        )

        self._page_stack = QStackedWidget()

        root_widget = QWidget()
        root_layout = QHBoxLayout(
            root_widget
        )
        root_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        root_layout.setSpacing(
            0
        )

        root_layout.addWidget(
            self._build_sidebar()
        )
        root_layout.addWidget(
            self._build_content_panel(),
            stretch=1,
        )

        self.setCentralWidget(
            root_widget
        )

        status_bar = QStatusBar(
            self
        )
        status_bar.showMessage(
            "Backend connected | Direct analysis workspace"
        )
        self.setStatusBar(
            status_bar
        )

        self._button_group.idClicked.connect(
            self.select_page
        )

        self.select_page(
            0
        )

    @property
    def navigation_keys(
        self,
    ) -> tuple[str, ...]:
        """Return the configured module keys."""

        return tuple(
            item.key
            for item in NAVIGATION_ITEMS
        )

    @property
    def active_page_key(
        self,
    ) -> str:
        """Return the key of the visible module page."""

        index = self._page_stack.currentIndex()

        if (
            index < 0
            or index >= len(
                NAVIGATION_ITEMS
            )
        ):
            return ""

        return NAVIGATION_ITEMS[
            index
        ].key

    @property
    def running_analysis_titles(
        self,
    ) -> tuple[str, ...]:
        """Return investigator-facing titles for active analyses."""

        titles: list[str] = []

        for index, item in enumerate(
            NAVIGATION_ITEMS
        ):
            page = self._page_stack.widget(
                index
            )

            if bool(
                getattr(
                    page,
                    "is_running",
                    False,
                )
            ):
                titles.append(
                    item.title
                )

        return tuple(
            titles
        )

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        """Keep active analysis threads alive until work completes."""

        running_titles = self.running_analysis_titles

        if running_titles:
            event.ignore()
            analysis_text = ", ".join(
                running_titles
            )
            message = (
                f"{analysis_text} is still running. Keep the application "
                "open until the analysis finishes. Closing now could "
                "interrupt report generation."
            )
            self.statusBar().showMessage(
                message
            )
            QMessageBox.warning(
                self,
                "Analysis in Progress",
                message,
            )
            return

        super().closeEvent(
            event
        )

    def _build_sidebar(
        self,
    ) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName(
            "sidebar"
        )
        sidebar.setFixedWidth(
            270
        )

        layout = QVBoxLayout(
            sidebar
        )
        layout.setContentsMargins(
            20,
            24,
            20,
            20,
        )
        layout.setSpacing(
            8
        )

        brand_title = QLabel(
            "TELECOM FORENSICS"
        )
        brand_title.setObjectName(
            "brandTitle"
        )

        brand_subtitle = QLabel(
            "Investigation Analysis Suite"
        )
        brand_subtitle.setObjectName(
            "brandSubtitle"
        )

        section_label = QLabel(
            "ANALYSIS WORKSPACE"
        )
        section_label.setObjectName(
            "sectionLabel"
        )

        layout.addWidget(
            brand_title
        )
        layout.addWidget(
            brand_subtitle
        )
        layout.addSpacing(
            24
        )
        layout.addWidget(
            section_label
        )
        layout.addSpacing(
            4
        )

        for index, item in enumerate(
            NAVIGATION_ITEMS
        ):
            button = QPushButton(
                item.title
            )
            button.setObjectName(
                "navButton"
            )
            button.setCheckable(
                True
            )
            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
            button.setToolTip(
                item.description
            )

            self._button_group.addButton(
                button,
                index,
            )
            self._navigation_buttons.append(
                button
            )

            layout.addWidget(
                button
            )

        layout.addItem(
            QSpacerItem(
                20,
                20,
                QSizePolicy.Policy.Minimum,
                QSizePolicy.Policy.Expanding,
            )
        )

        close_button = QPushButton(
            "Close Application"
        )
        close_button.setObjectName(
            "closeButton"
        )
        close_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        close_button.clicked.connect(
            self.close
        )

        layout.addWidget(
            close_button
        )

        return sidebar

    def _build_content_panel(
        self,
    ) -> QFrame:
        panel = QFrame()
        panel.setObjectName(
            "contentPanel"
        )

        layout = QVBoxLayout(
            panel
        )
        layout.setContentsMargins(
            34,
            26,
            34,
            28,
        )
        layout.setSpacing(
            20
        )

        header = QVBoxLayout()
        header.setSpacing(
            5
        )
        header.addWidget(
            self._page_title
        )
        header.addWidget(
            self._page_subtitle
        )

        page_factories = {
            "cdr": CdrPage,
            "tower_dump": TowerDumpPage,
            "ipdr": IpdrPage,
            "imei": ImeiPage,
            "lookup": LookupPage,
            "case_details": CaseDetailsPage,
            "case_reports": CaseReportsPage,
        }

        for item in NAVIGATION_ITEMS:
            try:
                page_factory = page_factories[item.key]
            except KeyError as error:
                raise RuntimeError(
                    f"No GUI page is registered for: {item.key}"
                ) from error

            page = page_factory()
            self._page_stack.addWidget(
                page
            )

        layout.addLayout(
            header
        )
        layout.addWidget(
            self._page_stack,
            stretch=1,
        )

        return panel

    def select_page(
        self,
        index: int,
    ) -> None:
        """Display one module page by index."""

        if (
            index < 0
            or index >= len(
                NAVIGATION_ITEMS
            )
        ):
            raise IndexError(
                f"Invalid GUI page index: {index}"
            )

        item = NAVIGATION_ITEMS[
            index
        ]

        self._page_stack.setCurrentIndex(
            index
        )
        page = self._page_stack.widget(
            index
        )
        refresh = getattr(
            page,
            "refresh",
            None,
        )

        if callable(
            refresh
        ):
            refresh()
        self._navigation_buttons[
            index
        ].setChecked(
            True
        )

        self._page_title.setText(
            item.title
        )
        self._page_subtitle.setText(
            item.description
        )

        self.statusBar().showMessage(
            f"{item.title} | Backend ready"
        )

    def select_page_by_key(
        self,
        key: str,
    ) -> None:
        """Display one module page using its stable key."""

        for index, item in enumerate(
            NAVIGATION_ITEMS
        ):
            if item.key == key:
                self.select_page(
                    index
                )
                return

        raise KeyError(
            f"Unknown GUI page key: {key}"
        )
