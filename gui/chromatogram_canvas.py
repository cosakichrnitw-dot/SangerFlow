import tkinter as tk

from gui.chromatogram_read import ChromatogramRead


class ChromatogramCanvas(tk.Frame):

    def __init__(self, parent):

        super().__init__(
            parent,
            relief="groove",
            borderwidth=2
        )

        # =====================
        # Base layout settings
        # =====================

        self.base_row_height = 100
        self.base_trace_height = 70

        self.trace_top = 55
        self.sequence_y = 20
        self.ruler_y = 5

        # =====================
        # Display scales
        # =====================

        self.scale_x = 1.0
        self.scale_y = 1.0
        self.zoom_factor = 1.2

        # =====================
        # Horizontal scrollbar
        # =====================

        self.h_scrollbar = tk.Scrollbar(
            self,
            orient="horizontal"
        )

        self.h_scrollbar.pack(
            side="bottom",
            fill="x"
        )

        # =====================
        # Coordinate inspector
        # =====================

        self.inspector_frame = tk.LabelFrame(
            self,
            text="Selected Base"
        )

        self.inspector_frame.pack(
            side="bottom",
            fill="x",
            padx=4,
            pady=2
        )

        self.inspector_text = tk.StringVar()

        self.inspector_label = tk.Label(
            self.inspector_frame,
            textvariable=self.inspector_text,
            anchor="w",
            justify="left",
            font=(
                "Courier",
                9
            )
        )

        self.inspector_label.pack(
            fill="x",
            padx=6,
            pady=3
        )

        self._clear_inspector()

        # =====================
        # Main frame
        # =====================

        self.main_frame = tk.Frame(
            self
        )

        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=0,
            pady=0
        )

        # =====================
        # Fixed sample labels
        # =====================

        self.label_canvas = tk.Canvas(
            self.main_frame,
            width=110,
            bg="white",
            highlightthickness=0
        )

        self.label_canvas.pack(
            side="left",
            fill="y"
        )

        # =====================
        # APE-style scale bars
        # =====================

        # Two thin vertical controls placed side by side.
        # They intentionally use the same native scrollbar style
        # as the horizontal scrollbar at the bottom.

        self.scale_panel = tk.Frame(
            self.main_frame,
            width=38,
            bg="#F2F2F2",
            relief="flat",
            borderwidth=0
        )

        self.scale_panel.pack(
            side="right",
            fill="y"
        )

        self.scale_panel.pack_propagate(
            False
        )

        self.scale_bars_frame = tk.Frame(
            self.scale_panel,
            bg="#F2F2F2"
        )

        self.scale_bars_frame.pack(
            side="top",
            fill="both",
            expand=True
        )

        self.y_scale_scrollbar = tk.Scrollbar(
            self.scale_bars_frame,
            orient="vertical",
            command=self._on_y_scale_scroll
        )

        self.y_scale_scrollbar.pack(
            side="left",
            fill="y",
            expand=True
        )

        self.x_scale_scrollbar = tk.Scrollbar(
            self.scale_bars_frame,
            orient="vertical",
            command=self._on_x_scale_scroll
        )

        self.x_scale_scrollbar.pack(
            side="left",
            fill="y",
            expand=True
        )

        self.scale_labels_frame = tk.Frame(
            self.scale_panel,
            bg="#F2F2F2"
        )

        self.scale_labels_frame.pack(
            side="bottom",
            fill="x"
        )

        tk.Label(
            self.scale_labels_frame,
            text="y",
            font=("Arial", 9),
            bg="#F2F2F2"
        ).pack(
            side="left",
            expand=True
        )

        tk.Label(
            self.scale_labels_frame,
            text="x",
            font=("Arial", 9),
            bg="#F2F2F2"
        ).pack(
            side="left",
            expand=True
        )

        self._update_scale_scrollbars()

        # =====================
        # Chromatogram canvas
        # =====================

        self.canvas = tk.Canvas(
            self.main_frame,
            bg="white",
            highlightthickness=0,
            xscrollcommand=self.h_scrollbar.set
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.h_scrollbar.config(
            command=self.canvas.xview
        )

        # =====================
        # Data
        # =====================

        self.reads = []
        self.visible_reads = []

        self.show_trim_region = False

        # =====================
        # Current position marker
        # =====================

        self.current_position = None
        self.position_marker = None
        self.highlight_base = None

        # =====================
        # Mouse navigation
        # =====================

        self._bind_scroll_events()

        self.canvas.bind(
            "<Button-1>",
            self._on_base_click
        )

        self.canvas.bind(
            "<ButtonPress-2>",
            self.pan_start
        )

        self.canvas.bind(
            "<B2-Motion>",
            self.pan_move
        )

        self.canvas.bind(
            "<Shift-ButtonPress-1>",
            self.pan_start
        )

        self.canvas.bind(
            "<Shift-B1-Motion>",
            self.pan_move
        )

    # ==================================================
    # Current scaled dimensions
    # ==================================================

    def get_trace_height(self):

        return max(
            20,
            int(
                self.base_trace_height
                *
                self.scale_y
            )
        )

    def get_row_height(self):

        return max(
            self.base_row_height,
            int(
                self.trace_top
                +
                self.get_trace_height()
                /
                2
                +
                10
            )
        )

    # ==================================================
    # Scale callbacks
    # ==================================================

    X_SCALE_MIN = 0.3
    X_SCALE_MAX = 20.0
    Y_SCALE_MIN = 0.5
    Y_SCALE_MAX = 3.0
    SCALE_THUMB_SIZE = 0.08

    def _value_to_scroll_fraction(
        self,
        value,
        minimum,
        maximum
    ):

        if maximum <= minimum:

            return 0.0

        return min(
            1.0,
            max(
                0.0,
                (
                    maximum
                    -
                    value
                )
                /
                (
                    maximum
                    -
                    minimum
                )
            )
        )

    def _scroll_fraction_to_value(
        self,
        fraction,
        minimum,
        maximum
    ):

        fraction = min(
            1.0,
            max(
                0.0,
                fraction
            )
        )

        return (
            maximum
            -
            fraction
            *
            (
                maximum
                -
                minimum
            )
        )

    def _apply_scroll_command(
        self,
        args,
        current_fraction
    ):

        if not args:

            return current_fraction

        if args[0] == "moveto":

            return float(
                args[1]
            )

        if args[0] == "scroll":

            amount = int(
                args[1]
            )

            unit = args[2]

            step = (
                0.10
                if unit == "pages"
                else 0.02
            )

            return (
                current_fraction
                +
                amount
                *
                step
            )

        return current_fraction

    def _update_scale_scrollbars(self):

        y_fraction = self._value_to_scroll_fraction(
            self.scale_y,
            self.Y_SCALE_MIN,
            self.Y_SCALE_MAX
        )

        x_fraction = self._value_to_scroll_fraction(
            self.scale_x,
            self.X_SCALE_MIN,
            self.X_SCALE_MAX
        )

        self.y_scale_scrollbar.set(
            y_fraction,
            min(
                1.0,
                y_fraction
                +
                self.SCALE_THUMB_SIZE
            )
        )

        self.x_scale_scrollbar.set(
            x_fraction,
            min(
                1.0,
                x_fraction
                +
                self.SCALE_THUMB_SIZE
            )
        )

    def _on_x_scale_scroll(
        self,
        *args
    ):

        current_fraction = self._value_to_scroll_fraction(
            self.scale_x,
            self.X_SCALE_MIN,
            self.X_SCALE_MAX
        )

        fraction = self._apply_scroll_command(
            args,
            current_fraction
        )

        value = self._scroll_fraction_to_value(
            fraction,
            self.X_SCALE_MIN,
            self.X_SCALE_MAX
        )

        self.change_x_scale(
            value
        )

    def _on_y_scale_scroll(
        self,
        *args
    ):

        current_fraction = self._value_to_scroll_fraction(
            self.scale_y,
            self.Y_SCALE_MIN,
            self.Y_SCALE_MAX
        )

        fraction = self._apply_scroll_command(
            args,
            current_fraction
        )

        value = self._scroll_fraction_to_value(
            fraction,
            self.Y_SCALE_MIN,
            self.Y_SCALE_MAX
        )

        self.change_y_scale(
            value
        )

    def change_x_scale(
        self,
        value
    ):

        old_center = self._get_horizontal_center_fraction()

        self.scale_x = min(
            self.X_SCALE_MAX,
            max(
                self.X_SCALE_MIN,
                float(value)
            )
        )

        self._update_scale_scrollbars()
        self.draw()

        self._restore_horizontal_center_fraction(
            old_center
        )

    def change_y_scale(
        self,
        value
    ):

        old_y = self.canvas.yview()

        self.scale_y = min(
            self.Y_SCALE_MAX,
            max(
                self.Y_SCALE_MIN,
                float(value)
            )
        )

        self._update_scale_scrollbars()
        self.draw()

        if old_y:

            self.canvas.yview_moveto(
                old_y[0]
            )

            self.label_canvas.yview_moveto(
                old_y[0]
            )

    def _get_horizontal_center_fraction(self):

        bbox = self.canvas.bbox(
            "all"
        )

        if not bbox:

            return 0.0

        total_width = max(
            1,
            bbox[2]
            -
            bbox[0]
        )

        left_fraction = self.canvas.xview()[0]
        visible_width = self.canvas.winfo_width()

        return min(
            1.0,
            max(
                0.0,
                left_fraction
                +
                visible_width
                /
                (
                    2
                    *
                    total_width
                )
            )
        )

    def _restore_horizontal_center_fraction(
        self,
        center_fraction
    ):

        bbox = self.canvas.bbox(
            "all"
        )

        if not bbox:

            return

        total_width = max(
            1,
            bbox[2]
            -
            bbox[0]
        )

        visible_width = self.canvas.winfo_width()

        left_fraction = (
            center_fraction
            -
            visible_width
            /
            (
                2
                *
                total_width
            )
        )

        left_fraction = min(
            1.0,
            max(
                0.0,
                left_fraction
            )
        )

        self.canvas.xview_moveto(
            left_fraction
        )

    # ==================================================
    # Load single read
    # ==================================================

    def load_data(
        self,
        read
    ):

        self.reads = [
            read
        ]

        self.visible_reads = []

        self._clear_inspector()

        self.draw()
        self._reset_vertical_view()

    # ==================================================
    # Load multiple reads
    # ==================================================

    def load_reads(
        self,
        reads
    ):

        self.reads = reads

        self._clear_inspector()

        self.draw()
        self._reset_vertical_view()

    # ==================================================
    # Main draw
    # ==================================================

    def draw(self):

        self.canvas.delete(
            "all"
        )

        self.label_canvas.delete(
            "all"
        )

        if self.visible_reads:

            reads = self.visible_reads

        else:

            reads = self.reads

        if len(reads) == 0:

            self.canvas.config(
                scrollregion=(
                    0,
                    0,
                    0,
                    0
                )
            )

            self.label_canvas.config(
                scrollregion=(
                    0,
                    0,
                    110,
                    0
                )
            )

            return

        for i, read in enumerate(
            reads
        ):

            self.draw_single_read(
                read,
                i
            )

        bbox = self.canvas.bbox(
            "all"
        )

        if bbox:

            # Restrict vertical scrolling to the rows actually being drawn.
            # Canvas item bounds can include text or marker margins; they are
            # useful horizontally but should not create extra blank read rows.
            read_display_bottom = self._read_display_bottom(
                len(reads)
            )

            self.canvas.config(
                scrollregion=(
                    bbox[0],
                    0,
                    bbox[2],
                    read_display_bottom
                )
            )

            self.label_canvas.config(
                scrollregion=(
                    0,
                    0,
                    110,
                    read_display_bottom
                )
            )

        self._draw_position_marker()

    def _read_display_bottom(
        self,
        read_count
    ):
        """Return the lower edge of the last visible chromatogram row."""

        if read_count <= 0:
            return 0

        return (
            (read_count - 1)
            *
            self.get_row_height()
            +
            self.trace_top
            +
            self.get_trace_height()
        )

    def _reset_vertical_view(self):
        """Start a changed read selection at its first displayed row."""

        self.canvas.yview_moveto(
            0
        )

        self.label_canvas.yview_moveto(
            0
        )

    # ==================================================
    # Single read
    # ==================================================

    def draw_single_read(
        self,
        read,
        index
    ):

        row_height = self.get_row_height()

        y_offset = (
            index
            *
            row_height
        )

        self.label_canvas.create_text(
            5,
            y_offset
            +
            self.sequence_y,
            text=read.filename,
            anchor="w",
            font=(
                "Courier",
                9,
                "bold"
            )
        )

        viewer = ChromatogramRead(
            canvas=self.canvas,
            read=read,
            scale_x=self.scale_x,
            trace_top=self.trace_top,
            trace_height=self.get_trace_height(),
            sequence_y=self.sequence_y,
            ruler_y=self.ruler_y,
            y_offset=y_offset
        )

        viewer.show_trim_region = (
            self.show_trim_region
        )

        viewer.highlight_position = (
            self.highlight_base
        )

        viewer.draw()

    # ==================================================
    # Position marker
    # ==================================================

    def _draw_position_marker(self):

        self.position_marker = None

        if self.current_position is None:

            return

        bbox = self.canvas.bbox(
            "all"
        )

        if not bbox:

            return

        x = (
            self.current_position
            *
            self.scale_x
        )

        self.position_marker = self.canvas.create_line(
            x,
            bbox[1],
            x,
            bbox[3],
            fill="purple",
            width=2,
            dash=(
                4,
                2
            )
        )

    # ==================================================
    # Jump to alignment position
    # ==================================================

    def goto_position(
        self,
        position
    ):

        if position is None:

            return

        self.current_position = position
        self.highlight_base = position

        self.draw()

        bbox = self.canvas.bbox(
            "all"
        )

        if not bbox:

            return

        x = (
            position
            *
            self.scale_x
        )

        canvas_width = self.canvas.winfo_width()
        total_width = max(
            1,
            bbox[2]
        )

        if total_width <= canvas_width:

            return

        fraction = (
            x
            -
            canvas_width
            /
            2
        ) / total_width

        fraction = min(
            1.0,
            max(
                0.0,
                fraction
            )
        )

        self.canvas.xview_moveto(
            fraction
        )

    # ==================================================
    # Change visible reads only
    # ==================================================

    def set_visible_reads(
        self,
        reads
    ):

        self.visible_reads = reads

        self._clear_inspector()

        self.draw()
        self._reset_vertical_view()

    # ==================================================
    # Coordinate inspector
    # ==================================================

    def _clear_inspector(self):

        self.inspector_text.set(
            "Sample: —\n"
            "Base: —   Quality: —   Region: —\n"
            "Raw index (0-based): —   Trim index (0-based): —\n"
            "Raw trace: —   Trim trace: —"
        )

    def _on_base_click(
        self,
        event
    ):

        if event.state & 0x0001:

            return

        canvas_x = self.canvas.canvasx(
            event.x
        )

        canvas_y = self.canvas.canvasy(
            event.y
        )

        if canvas_y < 0:

            return

        if self.visible_reads:

            reads = self.visible_reads

        else:

            reads = self.reads

        row_height = self.get_row_height()

        row_index = int(
            canvas_y
            //
            row_height
        )

        if (
            row_index < 0
            or
            row_index >= len(reads)
        ):

            return

        read = reads[row_index]
        positions = read.base_positions

        if not positions:

            return

        raw_index = min(
            range(
                len(positions)
            ),
            key=lambda index: abs(
                positions[index]
                *
                self.scale_x
                -
                canvas_x
            )
        )

        self._show_base_coordinates(
            read,
            raw_index
        )

    def _show_base_coordinates(
        self,
        read,
        raw_index
    ):

        trim_start = read.trim_start
        trim_end = read.trim_end

        is_trimmed = (
            trim_start
            <=
            raw_index
            <
            trim_end
        )

        if is_trimmed:

            trimmed_index = (
                raw_index
                -
                trim_start
            )

            trimmed_trace_position = (
                read.trimmed_base_positions[
                    trimmed_index
                ]
            )

            region = "TRIMMED"

        else:

            trimmed_index = "—"
            trimmed_trace_position = "—"
            region = "OUTSIDE TRIM"

        self.inspector_text.set(
            f"Sample: {read.filename}\n"
            f"Base: {read.sequence[raw_index]}   "
            f"Quality: {read.quality[raw_index]}   "
            f"Region: {region}\n"
            f"Raw index (0-based): {raw_index}   "
            f"Trim index (0-based): {trimmed_index}\n"
            f"Raw trace: {read.base_positions[raw_index]}   "
            f"Trim trace: {trimmed_trace_position}"
        )

    # ==================================================
    # Mouse scroll / Zoom
    # ==================================================

    def _bind_scroll_events(self):

        scroll_targets = (
            self,
            self.main_frame,
            self.canvas,
            self.label_canvas,
        )

        for widget in scroll_targets:

            widget.bind(
                "<MouseWheel>",
                self.mouse_scroll
            )

            widget.bind(
                "<Shift-MouseWheel>",
                self.mouse_scroll
            )

    def _wheel_steps(
        self,
        delta
    ):

        if delta == 0:

            return 0

        if abs(delta) >= 120:

            return -int(
                delta
                /
                120
            )

        return -int(
            delta
        )

    def _scroll_vertical(
        self,
        steps
    ):

        if steps == 0:

            return

        self.canvas.yview_scroll(
            steps,
            "units"
        )

        self.label_canvas.yview_scroll(
            steps,
            "units"
        )

    def _scroll_horizontal(
        self,
        steps
    ):

        if steps == 0:

            return

        self.canvas.xview_scroll(
            steps,
            "units"
        )

    def mouse_scroll(
        self,
        event
    ):

        # Command + scroll = horizontal zoom

        if event.state & 0x0008:

            old_center = (
                self._get_horizontal_center_fraction()
            )

            if event.delta > 0:

                self.scale_x *= (
                    self.zoom_factor
                )

            else:

                self.scale_x /= (
                    self.zoom_factor
                )

            self.scale_x = min(
                20.0,
                max(
                    0.3,
                    self.scale_x
                )
            )

            self._update_scale_scrollbars()

            self.draw()

            self._restore_horizontal_center_fraction(
                old_center
            )

            return

        steps = self._wheel_steps(
            event.delta
        )

        # Mac horizontal trackpad / Shift + wheel

        if event.state & 0x0001:

            self._scroll_horizontal(
                steps
            )

            return

        self._scroll_vertical(
            steps
        )

    # ==================================================
    # Pan
    # ==================================================

    def pan_start(
        self,
        event
    ):

        self.canvas.scan_mark(
            event.x,
            event.y
        )

    def pan_move(
        self,
        event
    ):

        self.canvas.scan_dragto(
            event.x,
            event.y,
            gain=1
        )

    # ==================================================
    # Toggle Trim Region display
    # ==================================================

    def set_show_trim_region(
        self,
        value
    ):

        self.show_trim_region = value

        self.draw()
