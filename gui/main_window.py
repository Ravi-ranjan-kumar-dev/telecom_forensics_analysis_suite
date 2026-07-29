"""Main desktop window for the application."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)


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
        title="Case Reports",
        description=(
            "Open investigation reports created for the active case."
        ),
    ),
)


class ModulePage(QFrame):
    """Display the foundation screen for one application module."""

    def __init__(
        self,
        item: NavigationItem,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent
        )

        self.setObjectName(
            "pageSurface"
        )

        layout = QVBoxLayout(
            self
        )
        layout.setContentsMargins(
            32,
            30,
            32,
            30,
        )
        layout.setSpacing(
            22
        )

        heading_row = QHBoxLayout()
        heading_row.setSpacing(
            12
        )

        module_title = QLabel(
            item.title
        )
        module_title.setObjectName(
            "moduleTitle"
        )

        status_badge = QLabel(
            "BACKEND READY"
        )
        status_badge.setObjectName(
            "statusBadge"
        )
        status_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        heading_row.addWidget(
            module_title
        )
        heading_row.addStretch()
        heading_row.addWidget(
            status_badge
        )

        description = QLabel(
            item.description
        )
        description.setObjectName(
            "moduleDescription"
        )
        description.setWordWrap(
            True
        )

        information_card = QFrame()
        information_card.setObjectName(
            "infoCard"
        )

        card_layout = QVBoxLayout(
            information_card
        )
        card_layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )
        card_layout.setSpacing(
            14
        )

        card_heading = QLabel(
            "GUI Foundation Status"
        )
        card_heading.setObjectName(
            "cardHeading"
        )

        card_text = QLabel(
            "The screen is ready. Evidence selection, analysis "
            "controls and report actions will be connected to the "
            "existing backend in the next milestone."
        )
        card_text.setObjectName(
            "cardText"
        )
        card_text.setWordWrap(
            True
        )

        card_layout.addWidget(
            card_heading
        )
        card_layout.addWidget(
            card_text
        )

        workflow_card = QFrame()
        workflow_card.setObjectName(
            "infoCard"
        )

        workflow_layout = QVBoxLayout(
            workflow_card
        )
        workflow_layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )
        workflow_layout.setSpacing(
            14
        )

        workflow_heading = QLabel(
            "Planned Investigator Workflow"
        )
        workflow_heading.setObjectName(
            "cardHeading"
        )

        workflow_layout.addWidget(
            workflow_heading
        )

        workflow_steps = (
            "Select evidence or open the active case.",
            "Run the required analysis.",
            "Review findings and open the report.",
        )

        for number, text in enumerate(
            workflow_steps,
            start=1,
        ):
            step_row = QHBoxLayout()
            step_row.setSpacing(
                12
            )

            step_number = QLabel(
                str(number)
            )
            step_number.setObjectName(
                "stepNumber"
            )
            step_number.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            step_text = QLabel(
                text
            )
            step_text.setObjectName(
                "cardText"
            )
            step_text.setWordWrap(
                True
            )

            step_row.addWidget(
                step_number
            )
            step_row.addWidget(
                step_text,
                stretch=1,
            )

            workflow_layout.addLayout(
                step_row
            )

        layout.addLayout(
            heading_row
        )
        layout.addWidget(
            description
        )
        layout.addWidget(
            information_card
        )
        layout.addWidget(
            workflow_card
        )
        layout.addStretch()


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
            "Backend freeze active | GUI foundation"
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

        for item in NAVIGATION_ITEMS:
            self._page_stack.addWidget(
                ModulePage(
                    item
                )
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
