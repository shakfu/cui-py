/* cuix.c - the accessors in cuix.h. Those CUI 1.5 exposes call cui.h; the rest
   read struct cui_ctx from the private cui_internal.h. Build with CUI's own
   CUI_TEXT_SHAPING setting: it changes the struct's layout. */
#include "cui_internal.h"

#include "cuix.h"

int cuix_take_text(cui_ctx *ui, char *buf, int cap) {
    int n = ui->text_in_len < cap - 1 ? ui->text_in_len : cap - 1;
    if (n < 0) n = 0;
    memcpy(buf, ui->text_in, (size_t)n);
    buf[n] = 0;
    ui->text_in_len = 0;
    ui->text_in[0] = 0;
    return n;
}

void cuix_focus(cui_ctx *ui, cui_id id) { ui->focus = id; }
bool cuix_window_focused(cui_ctx *ui) { return cui_window_focused(ui); }
bool cuix_focused(cui_ctx *ui, cui_id id) { return id && cui_focused_id(ui) == id; }
void cuix_own_tab(cui_ctx *ui, cui_id id) { ui->tab_owner = id; }
void cuix_eat_key(cui_ctx *ui, cui_key key) { ui->kpressed[key] = 0; }

float cuix_take_scroll(cui_ctx *ui) {
    float dy = ui->scroll_dy;
    ui->scroll_dy = 0;
    return dy;
}

void cuix_set_cursor(cui_ctx *ui, cui_cursor cursor) { cui_set_cursor(ui, cursor); }
void cuix_set_clipboard(cui_ctx *ui, const char *utf8) { cui_set_clipboard_text(ui, utf8); }
const char *cuix_clipboard(cui_ctx *ui) { return cui_get_clipboard_text(ui); } /* "" when unavailable */
