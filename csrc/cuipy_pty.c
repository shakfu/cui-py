/* cuipy_pty.c - cuipy_pty.h over cui-repl's session and term_view. */
#include "cuipy_pty.h"

#include "session.h"
#include "term_view.h"

#include <errno.h>
#include <stdlib.h>

struct cuipy_pty {
    session s;
    term_view v;
};

const bool cuipy_pty_available = true;

cuipy_pty *cuipy_pty_open(char *const argv[], const char *cwd, float font_size) {
    cuipy_pty *p = calloc(1, sizeof *p);
    if (!p) return NULL;
    if (session_open(&p->s, argv, cwd, 80, 24) < 0) {
        int e = errno;
        session_close(&p->s);
        free(p);
        errno = e;
        return NULL;
    }
    if (term_view_init(&p->v, &p->s, font_size) < 0) {
        session_close(&p->s);
        free(p);
        errno = ENOMEM;
        return NULL;
    }
    return p;
}

void cuipy_pty_frame(cui_ctx *ui, cuipy_pty *p, const char *id) { term_view_frame(ui, &p->v, id); }
void cuipy_pty_send(cuipy_pty *p, const char *data, size_t n) { session_send(&p->s, data, n); }
char *cuipy_pty_screen(cuipy_pty *p, bool selection) { return session_format(&p->s, selection); }
const char *cuipy_pty_title(cuipy_pty *p) { return p->s.title; }
bool cuipy_pty_exited(cuipy_pty *p) { return p->s.exited; }
int cuipy_pty_exit_code(cuipy_pty *p) { return session_exit_code(&p->s); }

void cuipy_pty_close(cuipy_pty *p) {
    term_view_free(&p->v);
    session_close(&p->s);
    free(p);
}
