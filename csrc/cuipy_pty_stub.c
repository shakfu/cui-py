/* cuipy_pty_stub.c - cuipy_pty.h for builds without CUI_PY_PTY: open fails with ENOSYS. */
#include "cuipy_pty.h"

#include <errno.h>

const bool cuipy_pty_available = false;

cuipy_pty *cuipy_pty_open(char *const argv[], const char *cwd, float font_size) {
    (void)argv, (void)cwd, (void)font_size;
    errno = ENOSYS;
    return NULL;
}

/* Unreachable: no cuipy_pty exists. */
void cuipy_pty_frame(cui_ctx *ui, cuipy_pty *p, const char *id) { (void)ui, (void)p, (void)id; }
void cuipy_pty_send(cuipy_pty *p, const char *data, size_t n) { (void)p, (void)data, (void)n; }
char *cuipy_pty_screen(cuipy_pty *p, bool selection) { return (void)p, (void)selection, NULL; }
const char *cuipy_pty_title(cuipy_pty *p) { return (void)p, ""; }
bool cuipy_pty_exited(cuipy_pty *p) { return (void)p, true; }
int cuipy_pty_exit_code(cuipy_pty *p) { return (void)p, -1; }
void cuipy_pty_close(cuipy_pty *p) { (void)p; }
