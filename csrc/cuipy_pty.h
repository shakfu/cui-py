/* cuipy_pty.h - the api _core.pyx uses for cui.Pty. cuipy_pty.c implements it
   over thirdparty/cui-repl when CUI_PY_PTY is ON; cuipy_pty_stub.c otherwise. */
#ifndef CUIPY_PTY_H
#define CUIPY_PTY_H

#include "cui/cui.h"

#include <stdbool.h>
#include <stddef.h>

typedef struct cuipy_pty cuipy_pty;

extern const bool cuipy_pty_available;

/* Start argv (NULL: $SHELL, else /bin/sh) in cwd (NULL: ours). Returns NULL with
   errno set; ENOSYS when built without CUI_PY_PTY. */
cuipy_pty *cuipy_pty_open(char *const argv[], const char *cwd, float font_size);

/* Fill the space given with the terminal, handle input, pump the child's output. */
void cuipy_pty_frame(cui_ctx *ui, cuipy_pty *p, const char *id);

void cuipy_pty_send(cuipy_pty *p, const char *data, size_t n);

/* The screen, or the selection, as text; malloc'd, NULL when empty or on failure. */
char *cuipy_pty_screen(cuipy_pty *p, bool selection);

const char *cuipy_pty_title(cuipy_pty *p);
bool cuipy_pty_exited(cuipy_pty *p);
int cuipy_pty_exit_code(cuipy_pty *p); /* -1 while running */

/* Hang up the child (SIGHUP, SIGKILL after 0.5 s) and free p. */
void cuipy_pty_close(cuipy_pty *p);

#endif
