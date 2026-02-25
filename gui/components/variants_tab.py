"""
VariantsTab — High-Performance Variant Manager
===============================================
Architecture fix (this revision):
  BEFORE: header_frame → scroll_inner
          variants_frame → scroll_inner (appended AFTER all 307 headers → invisible)

  AFTER:  container_frame → scroll_inner
            header_frame  → container_frame
            variants_frame→ container_frame  ← always directly below header ✓

Threading model:
  Worker thread: pymysql query ONLY (never touches widgets)
  Main thread:   all widget creation/destruction via self.after(0, ...)
"""

import customtkinter as ctk
import threading
import webbrowser
import pymysql
import pymysql.cursors
from config.settings import settings

# ── Colours ────────────────────────────────────────────────────────────────
C_IN_STOCK = "#2ecc71"
C_SOLD_OUT = "#e74c3c"
C_EXCLUDED = "#7f8c8d"
C_UNKNOWN  = "#95a5a6"
C_HEADER   = "#2980b9"
C_ROW_A    = ("gray92", "gray18")
C_ROW_B    = ("gray86", "gray22")


def _db_connect():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
        read_timeout=15,
    )


def _bg(fn, on_done, on_err=None):
    """Run fn() in daemon thread. on_done/on_err must schedule via after()."""
    def _worker():
        try:
            result = fn()
            on_done(result)
        except Exception as exc:
            print(f"[_bg] exception: {exc}")
            if on_err:
                on_err(exc)
    threading.Thread(target=_worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════

class ProductRow:
    """
    One product entry. Layout:
      container_frame (→ scroll_inner)
        header_frame   (expand button + title + count)
        variants_frame (created on expand, destroyed on collapse)
    """

    def __init__(self, tab: 'VariantsTab', scroll_inner, product: dict):
        self.tab            = tab
        self.scroll_inner   = scroll_inner
        self.product_id     = product['id']
        self.title          = product.get('original_title') or f"Product #{product['id']}"
        self.product_url    = product.get('original_url') or ''
        self._variant_count = int(product.get('variant_count') or 0)
        self.variants_frame = None
        self._checkbox_vars: dict = {}
        self._expanded      = False
        self._loading       = False
        self._build()

    def _build(self):
        # ── Container: header + variants both live inside this ──────────────
        # KEY FIX: variants_frame packs INTO container, not into scroll_inner
        self.container = ctk.CTkFrame(self.scroll_inner, fg_color="transparent")
        self.container.pack(fill="x", pady=(2, 0), padx=2)

        # ── Header row ───────────────────────────────────────────────────────
        self._build_header()

    def _build_header(self):
        hdr = ctk.CTkFrame(self.container, corner_radius=5)
        hdr.pack(fill="x")
        hdr.grid_columnconfigure(1, weight=1)
        self.header_frame = hdr

        self.expand_btn = ctk.CTkButton(
            hdr, text="▶", width=30, height=26,
            fg_color="transparent",
            hover_color=("#d5dbdb", "#2c3e50"),
            text_color=C_HEADER,
            font=("Arial", 13, "bold"),
            command=self.toggle,
        )
        self.expand_btn.grid(row=0, column=0, padx=(6, 2), pady=4)

        short = self.title[:72] + "…" if len(self.title) > 72 else self.title
        ctk.CTkLabel(
            hdr, text=f"  {short}",
            font=("Arial", 12, "bold"),
            text_color=C_HEADER, anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=4)

        # 🔗 Link button — opens product URL in the default browser
        self.link_btn = ctk.CTkButton(
            hdr, text="🔗 Link", width=70, height=24,
            fg_color="transparent",
            hover_color=("#d5dbdb", "#2c3e50"),
            text_color=("#2471a3", "#5dade2"),
            font=("Arial", 11),
            cursor="hand2",
            command=lambda: webbrowser.open(self.product_url) if self.product_url else None,
        )
        self.link_btn.grid(row=0, column=2, padx=(0, 4))

        self.count_lbl = ctk.CTkLabel(
            hdr,
            text=f"{self._variant_count} variants" if self._variant_count else "",
            font=("Arial", 11), text_color=C_UNKNOWN, width=90,
        )
        self.count_lbl.grid(row=0, column=3, padx=(0, 8))

    # ── Toggle ───────────────────────────────────────────────────────────────

    def toggle(self):
        print(f"[ProductRow] toggle pid={self.product_id} expanded={self._expanded} loading={self._loading}")
        if self._loading:
            return
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self._loading or self._expanded:
            return
        self._loading = True

        # Immediate visual feedback — user sees ⏳ right away
        self.expand_btn.configure(text="⏳", state="disabled")
        print(f"[ProductRow] expand() → querying pid={self.product_id}")

        pid = self.product_id

        def _fetch():
            print(f"[ProductRow] _fetch() start pid={pid}")
            conn = _db_connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, option_name_1, option_name_2, status,
                               price_sale, price_orig, updated_at
                        FROM product_options
                        WHERE product_id = %s
                        ORDER BY option_name_1, option_name_2
                    """, (pid,))
                    rows = cur.fetchall()
                    print(f"[ProductRow] _fetch() done pid={pid} → {len(rows)} rows")
                    return rows
            finally:
                conn.close()

        _bg(
            _fetch,
            on_done=lambda rows: self.tab.after(0, self._on_loaded, rows),
            on_err =lambda e:    self.tab.after(0, self._on_err, e),
        )

    def _on_loaded(self, variants):
        print(f"[ProductRow] _on_loaded pid={self.product_id} variants={len(variants) if variants else 0}")
        self._loading = False
        self.expand_btn.configure(state="normal")

        if not variants:
            self.expand_btn.configure(text="—")
            return

        self._expanded = True
        self._variant_count = len(variants)
        self.count_lbl.configure(text=f"{self._variant_count} variants")
        self.expand_btn.configure(text="▼")

        # variants_frame packs INTO container → appears immediately below header
        self.variants_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.variants_frame.pack(fill="x", padx=(28, 2), pady=(0, 4))

        # Column header once
        ch = ctk.CTkFrame(self.variants_frame, fg_color="transparent")
        ch.pack(fill="x", pady=(1, 0))
        for col, (txt, w) in enumerate([
            ("✓", 36), ("Color", 130), ("Size", 90),
            ("Status", 82), ("$Sale", 62), ("Last Check", 110),
        ]):
            ctk.CTkLabel(
                ch, text=txt, width=w,
                font=("Arial", 10, "bold"),
                anchor="w" if col > 0 else "center",
            ).grid(row=0, column=col, padx=1)

        for idx, v in enumerate(variants):
            self._build_variant_row(v, idx)

        # Force canvas scroll-region update
        try:
            self.tab.scroll.update_idletasks()
        except Exception:
            pass

        print(f"[ProductRow] _on_loaded DONE — {len(variants)} rows rendered for pid={self.product_id}")

    def _on_err(self, exc):
        print(f"[ProductRow] _on_err pid={self.product_id}: {exc}")
        self._loading = False
        self.expand_btn.configure(text="❌", state="normal")

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self.expand_btn.configure(text="▶")
        if self.variants_frame:
            self.variants_frame.destroy()
            self.variants_frame = None
            self._checkbox_vars.clear()
        print(f"[ProductRow] collapsed pid={self.product_id}")

    # ── Variant row ──────────────────────────────────────────────────────────

    def _build_variant_row(self, v: dict, idx: int):
        opt_id  = v['id']
        status  = v.get('status')
        color   = v.get('option_name_1') or '—'
        size    = v.get('option_name_2') or '—'
        price   = v.get('price_sale')
        updated = v.get('updated_at')

        if status == -1:  s_txt, s_clr = "Excluded", C_EXCLUDED
        elif status == 1: s_txt, s_clr = "In Stock",  C_IN_STOCK
        elif status == 0: s_txt, s_clr = "Sold Out",  C_SOLD_OUT
        else:             s_txt, s_clr = "Unknown",   C_UNKNOWN

        p_txt = f"${float(price):.2f}" if price and float(price) > 0 else "—"
        u_txt = updated.strftime("%m/%d %H:%M") if updated else "Never"

        bg  = C_ROW_A if idx % 2 == 0 else C_ROW_B
        row = ctk.CTkFrame(self.variants_frame, fg_color=bg, corner_radius=3)
        row.pack(fill="x", pady=1)

        var = ctk.BooleanVar(value=(status != -1))
        self._checkbox_vars[opt_id] = var
        ctk.CTkCheckBox(
            row, text="", variable=var,
            width=36, checkbox_width=16, checkbox_height=16,
            command=lambda oid=opt_id, bv=var: self._on_chk(oid, bv),
        ).grid(row=0, column=0, padx=(4, 0), pady=3)

        ctk.CTkLabel(row, text=color, width=130, anchor="w", font=("Arial", 11)).grid(row=0, column=1, sticky="w", padx=2)
        ctk.CTkLabel(row, text=size,  width=90,  anchor="w", font=("Arial", 11)).grid(row=0, column=2, sticky="w")
        ctk.CTkLabel(row, text=s_txt, width=82,  text_color=s_clr, font=("Arial", 11, "bold")).grid(row=0, column=3)
        ctk.CTkLabel(row, text=p_txt, width=62,  font=("Arial", 11)).grid(row=0, column=4)
        ctk.CTkLabel(row, text=u_txt, width=110, text_color=C_UNKNOWN, font=("Arial", 10)).grid(row=0, column=5, padx=(0, 4))

    def _on_chk(self, option_id: int, var: ctk.BooleanVar):
        active = var.get()
        def _update():
            conn = _db_connect()
            try:
                with conn.cursor() as cur:
                    if active:
                        cur.execute(
                            "UPDATE product_options SET status=1, updated_at=NOW() WHERE id=%s AND status=-1",
                            (option_id,)
                        )
                    else:
                        cur.execute(
                            "UPDATE product_options SET status=-1, updated_at=NOW() WHERE id=%s",
                            (option_id,)
                        )
                conn.commit()
                return True
            finally:
                conn.close()

        _bg(
            _update,
            on_done=lambda _: self.tab.after(0, lambda: self.tab._toggle_done(option_id, active)),
            on_err =lambda e: self.tab.after(0, lambda: (
                self.tab._toggle_done(option_id, active, e),
                var.set(not active)
            )),
        )

    # ── Visibility for search ────────────────────────────────────────────────

    def matches(self, q: str) -> bool:
        return not q or q in self.title.lower()

    def show(self):
        self.container.pack(fill="x", pady=(2, 0), padx=2)

    def hide(self):
        if self._expanded:
            self.collapse()
        self.container.pack_forget()

    def destroy_all(self):
        if self._expanded:
            self.collapse()
        self.container.destroy()


# ══════════════════════════════════════════════════════════════════════════════

class VariantsTab(ctk.CTkFrame):
    """Products 🗂️ tab: lazy headers, on-demand variant expansion."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._rows: list[ProductRow] = []
        self._loading = False

        # ── Toolbar ─────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        tb.grid_columnconfigure(1, weight=1)

        self.btn_refresh = ctk.CTkButton(
            tb, text="🔄 Refresh", width=100, command=self.refresh
        )
        self.btn_refresh.grid(row=0, column=0, padx=(0, 8))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_search())
        ctk.CTkEntry(
            tb, textvariable=self.search_var,
            placeholder_text="🔍 Search product title…"
        ).grid(row=0, column=1, sticky="ew")

        self.status_lbl = ctk.CTkLabel(
            tb, text="Waiting for data…", text_color=C_UNKNOWN,
            width=260, anchor="e"
        )
        self.status_lbl.grid(row=0, column=2, padx=(8, 0))

        # ── Legend ───────────────────────────────────────────────────────────
        leg = ctk.CTkFrame(self, fg_color="transparent")
        leg.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 2))
        for txt, clr in [
            ("● In Stock", C_IN_STOCK), ("● Sold Out", C_SOLD_OUT),
            ("● Excluded", C_EXCLUDED), ("● Unknown",  C_UNKNOWN),
        ]:
            ctk.CTkLabel(leg, text=txt, text_color=clr,
                         font=("Arial", 11)).pack(side="left", padx=6)

        # ── Scrollable frame ─────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))

        try:
            self._inner = self.scroll._scrollable_frame
        except AttributeError:
            self._inner = self.scroll

        print(f"[VariantsTab] scroll inner frame: {self._inner}")

        # Deferred first load — ensures scroll frame is fully mapped
        self.after(300, self.refresh)

    # ── Data loading ─────────────────────────────────────────────────────────

    def refresh(self):
        if self._loading:
            print("[VariantsTab] refresh() blocked — already loading")
            return
        self._loading = True
        self.btn_refresh.configure(state="disabled", text="⏳ Loading…")
        self.status_lbl.configure(text="Connecting to DB…", text_color=C_UNKNOWN)
        self.search_var.set("")
        self._clear()
        print("[VariantsTab] refresh() → fetching product list…")

        def _fetch():
            conn = _db_connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT p.id, p.original_title, p.original_url,
                               COUNT(o.id) AS variant_count
                        FROM products p
                        LEFT JOIN product_options o ON o.product_id = p.id
                        GROUP BY p.id, p.original_title, p.original_url
                        ORDER BY p.id ASC
                    """)
                    rows = cur.fetchall()
                    print(f"[VariantsTab] fetched {len(rows)} products")
                    return rows
            finally:
                conn.close()

        _bg(
            _fetch,
            on_done=lambda rows: self.after(0, self._render_products, rows),
            on_err =lambda e:    self.after(0, self._on_load_err, e),
        )

    def _render_products(self, products: list):
        self._loading = False
        self.btn_refresh.configure(state="normal", text="🔄 Refresh")

        total = sum(int(p.get('variant_count') or 0) for p in products)
        self.status_lbl.configure(
            text=f"{len(products)} products · {total} variants  ▶ click to expand",
            text_color=C_UNKNOWN,
        )
        print(f"[VariantsTab] rendering {len(products)} headers into {self._inner}")

        for p in products:
            row = ProductRow(self, self._inner, p)
            self._rows.append(row)

        self.scroll.update_idletasks()
        print(f"[VariantsTab] render complete — {len(self._rows)} rows")

    def _on_load_err(self, exc):
        self._loading = False
        self.btn_refresh.configure(state="normal", text="🔄 Refresh")
        self.status_lbl.configure(text=f"❌ {exc}", text_color="#e74c3c")
        print(f"[VariantsTab] load error: {exc}")

    # ── Search ────────────────────────────────────────────────────────────────

    def _apply_search(self):
        q = self.search_var.get().strip().lower()
        matched = 0
        for row in self._rows:
            if row.matches(q):
                row.show()
                matched += 1
            else:
                row.hide()
        if q:
            self.status_lbl.configure(
                text=f"Showing {matched} of {len(self._rows)} products"
            )

    # ── Toggle result ──────────────────────────────────────────────────────────

    def _toggle_done(self, option_id: int, active: bool, err=None):
        if err:
            self.status_lbl.configure(
                text=f"❌ DB error #{option_id}: {err}", text_color="#e74c3c"
            )
        else:
            action = "✅ Enabled" if active else "🚫 Excluded"
            self.status_lbl.configure(
                text=f"{action} variant #{option_id}",
                text_color=C_IN_STOCK if active else C_EXCLUDED,
            )

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def _clear(self):
        for row in self._rows:
            row.destroy_all()
        self._rows.clear()
        print("[VariantsTab] cleared all rows")
