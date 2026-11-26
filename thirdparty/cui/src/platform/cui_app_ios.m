/* iOS backend (iOS 11+). UIApplicationMain on the main thread owns UIKit
 * (window, view, touches, the hidden text field); the app's main() runs on a
 * second thread: the delegate launches it as cui_ios_user_main, apps rename
 * their main by including cui/cui_ios_main.h. Touches and keyboard text are
 * posted to a mutex-guarded queue and drained by cui__plat_wait on the app
 * thread, so all cui_input_* calls happen where the frames run. Touch maps
 * to the mouse (first finger = left button). GL is EAGLContext (GLES3) on
 * the view's CAEAGLLayer; the software renderer puts a CGImage on the layer.
 * Compile with -fobjc-arc. */
#include "cui_platform.h"

#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <OpenGLES/EAGL.h>
#import <OpenGLES/ES3/gl.h>
#import <OpenGLES/ES3/glext.h>
#include <dlfcn.h>
#include <pthread.h>
#include <unistd.h>

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

@class CUIIOSView;

int cui_ios_user_main(int argc, char **argv);

@interface CUIIOSPlat : NSObject <UIApplicationDelegate, UITextFieldDelegate>
@property (nonatomic, strong) UIWindow *window;
@property (nonatomic, strong) CUIIOSView *view;
@property (nonatomic, strong) UITextField *field;
@property (nonatomic, strong) EAGLContext *gl;
@property (nonatomic, assign) cui_app *app;
@property (nonatomic, assign) BOOL kb_shown;   /* soft keyboard requested for the current editing session */
@end

@interface CUIIOSView : UIView
@property (nonatomic, assign) cui_app *app;
@property (nonatomic, assign) unsigned int framebuffer;
@property (nonatomic, assign) unsigned int renderbuffer;
@property (nonatomic, assign) int fb_width, fb_height;   /* actual renderbuffer pixel size */
@property (nonatomic, assign) CGFloat lay_w, lay_h;      /* last size seen in layoutSubviews */
@end

/* Backspace with an empty field never reaches shouldChangeCharactersInRange:
 * UIKit calls deleteBackward directly, so the subclass forwards it as a key */
@interface CUIIOSField : UITextField
@end

/* set by the delegate once UIApplicationMain has built the window */
static CUIIOSPlat *cui__ios_plat;
static CUIIOSPlat *cui__ios_p(cui_app *app) { return app->plat ? (__bridge CUIIOSPlat *)app->plat : cui__ios_plat; }
int cui__ios_argc;
char **cui__ios_argv;
/* NO while the app is active; YES from resign-active until did-become-active.
 * iOS terminates any app that issues GL calls in the background, so the
 * frame loop must not present while it is set. */
static bool cui__ios_paused;

/* ---- pending input from the main thread, drained on the app thread ---- */

enum { CUIIOS_MOVE, CUIIOS_DOWN, CUIIOS_UP, CUIIOS_TEXT, CUIIOS_KEY, CUIIOS_REDRAW };

typedef struct cui__ios_event {
    int kind;
    float x, y;
    cui_key key;
    bool key_down;
    struct cui__ios_event *next;
    char utf8[];   /* flexible: sized by the poster, so no composed sequence is ever truncated */
} cui__ios_event;

static pthread_mutex_t cui__ios_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cui__ios_wake = PTHREAD_COND_INITIALIZER;
static cui__ios_event *cui__ios_head, *cui__ios_tail;

static void cui__ios_post(cui__ios_event *e) {
    e->next = NULL;
    pthread_mutex_lock(&cui__ios_lock);
    if (cui__ios_tail) cui__ios_tail->next = e; else cui__ios_head = e;
    cui__ios_tail = e;
    pthread_cond_signal(&cui__ios_wake);
    pthread_mutex_unlock(&cui__ios_lock);
}

static void cui__ios_drain(cui_ctx *ui) {
    pthread_mutex_lock(&cui__ios_lock);
    cui__ios_event *list = cui__ios_head;
    cui__ios_head = cui__ios_tail = NULL;
    pthread_mutex_unlock(&cui__ios_lock);
    while (list) {
        cui__ios_event *e = list;
        list = e->next;
        switch (e->kind) {
        case CUIIOS_MOVE: cui_input_mouse_move(ui, e->x, e->y); break;
        case CUIIOS_DOWN:
            cui_input_mouse_move(ui, e->x, e->y);
            cui_input_mouse_button(ui, CUI_MOUSE_LEFT, true);
            break;
        case CUIIOS_UP:
            cui_input_mouse_move(ui, e->x, e->y);
            cui_input_mouse_button(ui, CUI_MOUSE_LEFT, false);
            break;
        case CUIIOS_TEXT: cui_input_text(ui, e->utf8); break;
        case CUIIOS_KEY: cui_input_key(ui, e->key, e->key_down, 0); break;
        case CUIIOS_REDRAW: cui_request_redraw(ui); break;   /* rotation resized the view */
        }
        free(e);
    }
}

double cui__plat_now(void) { return [[NSProcessInfo processInfo] systemUptime]; }
const char *cui__plat_name(void) { return "ios"; }

int cui__plat_system_dark(void) {
    if (@available(iOS 13.0, *))
        return [UITraitCollection currentTraitCollection].userInterfaceStyle == UIUserInterfaceStyleDark ? 1 : 0;
    return -1;
}

@implementation CUIIOSView
+ (Class)layerClass { return [CAEAGLLayer class]; }

/* Touches arrive here via the responder chain — the app delegate never
 * receives them. */
- (void)touchesBegan:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e {
    (void)e;
    CGPoint p = [t.anyObject locationInView:self];
    cui__ios_event *ev = calloc(1, sizeof *ev);
    ev->kind = CUIIOS_DOWN; ev->x = (float)p.x; ev->y = (float)p.y;
    cui__ios_post(ev);
}
- (void)touchesMoved:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e {
    (void)e;
    CGPoint p = [t.anyObject locationInView:self];
    cui__ios_event *ev = calloc(1, sizeof *ev);
    ev->kind = CUIIOS_MOVE; ev->x = (float)p.x; ev->y = (float)p.y;
    cui__ios_post(ev);
}
- (void)touchesEnded:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e {
    (void)e;
    CGPoint p = [t.anyObject locationInView:self];
    cui__ios_event *ev = calloc(1, sizeof *ev);
    ev->kind = CUIIOS_UP; ev->x = (float)p.x; ev->y = (float)p.y;
    cui__ios_post(ev);
}
- (void)touchesCancelled:(NSSet<UITouch *> *)t withEvent:(UIEvent *)e {
    (void)t; (void)e;
    cui__ios_event *ev = calloc(1, sizeof *ev);
    ev->kind = CUIIOS_UP;
    cui__ios_post(ev);
}

/* rotation and any relayout change the drawable size; remember the size and
 * wake the app thread so the next frame re-checks and, in the GL path,
 * reallocates the renderbuffer when it no longer matches. contentsScale is
 * a layer property, so it is written here on the main thread it belongs to. */
- (void)layoutSubviews {
    [super layoutSubviews];
    CGFloat sc = self.window.screen ? self.window.screen.scale : [UIScreen mainScreen].scale;
    if (self.layer.contentsScale != sc) self.layer.contentsScale = sc;
    if (self.bounds.size.width == self.lay_w && self.bounds.size.height == self.lay_h) return;
    self.lay_w = self.bounds.size.width;
    self.lay_h = self.bounds.size.height;
    cui__ios_event *ev = calloc(1, sizeof *ev);
    if (ev) { ev->kind = CUIIOS_REDRAW; cui__ios_post(ev); }
}
@end

static void cui__ios_post_key(int key) {
    for (int down = 1; down >= 0; down--) {
        cui__ios_event *ev = calloc(1, sizeof *ev);
        if (!ev) continue;
        ev->kind = CUIIOS_KEY;
        ev->key = key;
        ev->key_down = down;
        cui__ios_post(ev);
    }
}

@implementation CUIIOSField
- (void)deleteBackward {
    /* with the field empty the delegate callback never fires */
    cui__ios_post_key(CUI_KEY_BACKSPACE);
}
@end
@implementation CUIIOSPlat

/* The hidden field takes soft-keyboard input; we swallow the characters it
 * would insert ourselves so the CUI text edit owns the text. */
- (BOOL)textField:(UITextField *)f shouldChangeCharactersInRange:(NSRange)r replacementString:(NSString *)s {
    (void)f;
    /* the return key arrives as a newline replacement */
    if ([s isEqualToString:@"\n"]) {
        cui__ios_post_key(CUI_KEY_ENTER);
        return NO;
    }
    if (s.length == 0) {
        /* an empty replacement is a backspace; when the hidden field is
         * empty the range is empty too, so key it regardless of r.length */
        cui__ios_post_key(CUI_KEY_BACKSPACE);
        /* keep the delete key alive: the field text is a proxy, not content */
        f.text = @"aa";
        return NO;
    }
    for (NSUInteger i = 0; i < s.length; ) {
        NSRange br = [s rangeOfComposedCharacterSequenceAtIndex:i];
        NSString *sub = [s substringWithRange:br];
        /* one composed sequence is UTF-8 of at most 4 bytes per scalar times
         * the scalars in the cluster; UTF16 length bounds the scalar count */
        NSUInteger cap = sub.length * 4 + 1;
        cui__ios_event *ev = calloc(1, sizeof *ev + cap);
        if (!ev) { i += br.length; continue; }
        ev->kind = CUIIOS_TEXT;
        NSUInteger used = 0;
        [sub getBytes:ev->utf8 maxLength:cap usedLength:&used encoding:NSUTF8StringEncoding options:0 range:NSMakeRange(0, sub.length) remainingRange:NULL];
        ev->utf8[used] = 0;
        cui__ios_post(ev);
        i += br.length;
    }
    return NO;
}

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    (void)application; (void)launchOptions;
    self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    CUIIOSView *v = [[CUIIOSView alloc] initWithFrame:self.window.bounds];
    v.app = self.app;
    UIViewController *vc = [UIViewController new];
    vc.view = v;
    self.window.rootViewController = vc;
    self.view = v;
    self.field = [[UITextField alloc] initWithFrame:CGRectMake(0, 0, 1, 1)];
    self.field.autocorrectionType = UITextAutocorrectionTypeNo;
    self.field.autocapitalizationType = UITextAutocapitalizationTypeNone;
    self.field.delegate = self;
    self.field.text = @"aa";   /* keep the delete key enabled; deletions get re-seeded below */
    [v addSubview:self.field];
    [self.window makeKeyAndVisible];
    cui__ios_plat = self;
    /* the app's main (renamed cui_ios_user_main) runs on its own thread */
    [NSThread detachNewThreadSelector:@selector(runUserMain) toTarget:self withObject:nil];
    return YES;
}

- (void)textFieldDidEndEditing:(UITextField *)f {
    (void)f;
    self.kb_shown = NO;
}

- (UIInterfaceOrientationMask)application:(UIApplication *)application supportedInterfaceOrientationsForWindow:(UIWindow *)window {
    (void)application; (void)window;
    return UIInterfaceOrientationMaskAllButUpsideDown;
}

- (void)applicationDidBecomeActive:(UIApplication *)application {
    (void)application;
    /* at launch the window starts at a provisional 320x480 until the scene
     * connects; adopt the real bounds then. Only repair the provisional
     * size: under Split View / Slide Over the window is legitimately
     * smaller than the screen and must keep its assigned region. */
    CGSize screen = [UIScreen mainScreen].bounds.size;
    CGSize frame = self.window.frame.size;
    BOOL provisional = (frame.width <= 320.5 && frame.height <= 480.5) &&
        (screen.width > 320.5 || screen.height > 480.5);
    if (provisional) {
        /* setFrame, not setBounds: bounds keep the old center, leaving
         * the resized window displaced off the display */
        self.window.frame = [UIScreen mainScreen].bounds;
        self.view.frame = self.window.bounds;
        [self.view setNeedsLayout];
        [self.view layoutIfNeeded];
    }
    /* GL must not touch the GPU in the background (iOS kills the app);
     * the frame loop checks this flag before presenting */
    cui__ios_paused = NO;
}

- (void)applicationWillResignActive:(UIApplication *)application {
    (void)application;
    cui__ios_paused = YES;
}

- (void)runUserMain {
    @autoreleasepool {
        cui_ios_user_main(cui__ios_argc, cui__ios_argv);
        /* the app loop is over: leave UIKit running so the process exits cleanly */
        exit(0);
    }
}

@end

/* The app includes cui/cui_ios_main.h, which renames its main to
 * cui_ios_user_main; this file provides the real main. */
extern int cui_ios_user_main(int argc, char **argv);

int main(int argc, char *argv[]) {
    cui__ios_argc = argc;
    cui__ios_argv = argv;
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([CUIIOSPlat class]));
    }
}

/* ---- dialogs and URLs ----
 * iOS has no osascript or "open": the URL goes through UIApplication,
 * and dialogs report "not available". The Apple subprocess branch in
 * cui_dialogs.c is compiled out on iPhone by the same TARGET_OS_IPHONE
 * test used there. */

bool cui__plat_open_url(const char *url) {
    if (!url || !*url) return false;
    UIApplication *app = [UIApplication sharedApplication];
    NSURL *u = [NSURL URLWithString:@(url)];
    if (!u) return false;
    /* openURL:options:completionHandler: is iOS 10+; the backend targets 11.
     * The selector returns void: the completion handler carries the result. */
    __block bool ok = false;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    [app openURL:u options:@{} completionHandler:^(bool success) {
        ok = success;
        dispatch_semaphore_signal(done);
    }];
    /* wait a moment so the caller reliably learns whether it launched */
    dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)10 * NSEC_PER_SEC));
    return ok;
}

bool cui__plat_file_dialog(cui_app *app, const cui_file_dialog_opts *o, char *out, size_t cap) {
    (void)app; (void)o;
    if (cap) out[0] = 0;
    return false;
}

/* ---- GL: EAGLContext on the view's CAEAGLLayer ---- */

bool cui__plat_gl_create(cui_app *app, bool vsync) {
    (void)vsync;   /* presentRenderbuffer waits for the display, no interval knob */
    CUIIOSPlat *p = cui__ios_p(app);
    CUIIOSView *v = p.view;
    if (!v) return false;
    EAGLContext *ctx = [[EAGLContext alloc] initWithAPI:kEAGLRenderingAPIOpenGLES3];
    if (!ctx || ![EAGLContext setCurrentContext:ctx]) return false;
    CAEAGLLayer *layer = (CAEAGLLayer *)v.layer;
    /* On the simulator the CAEAGLLayer drawable never composites (render and
     * present succeed, screen stays black), while the plain-CALayer fallback
     * path works; on a device the layer is real and GL is used. The check
     * sits after setCurrentContext so a bail never strands the context. */
    if (![layer isKindOfClass:[CAEAGLLayer class]] ||
        NSProcessInfo.processInfo.environment[@"SIMULATOR_DEVICE_NAME"] != nil) {
        [EAGLContext setCurrentContext:nil];
        return false;
    }
    p.gl = ctx;
    layer.opaque = YES;
    CGFloat scale = p.window.screen ? p.window.screen.scale : [UIScreen mainScreen].scale;
    layer.contentsScale = scale;
    layer.drawableProperties = @{ kEAGLDrawablePropertyRetainedBacking : @NO,
                                  kEAGLColorFormatRGBA8 : @YES };
    unsigned fb = 0, rb = 0;
    glGenFramebuffers(1, &fb);
    glBindFramebuffer(GL_FRAMEBUFFER, fb);
    glGenRenderbuffers(1, &rb);
    glBindRenderbuffer(GL_RENDERBUFFER, rb);
    [ctx renderbufferStorage:GL_RENDERBUFFER fromDrawable:layer];
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        glDeleteFramebuffers(1, &fb);
        glDeleteRenderbuffers(1, &rb);
        p.gl = nil;
        return false;
    }
    /* the allocated renderbuffer's actual pixel size is what the renderer
     * must fill; ask GL rather than deriving it from bounds * scale */
    GLint rbw = 0, rbh = 0;
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &rbw);
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &rbh);
    v.fb_width = (int)rbw;
    v.fb_height = (int)rbh;
    v.framebuffer = fb;
    v.renderbuffer = rb;
    return true;
}

void *cui__plat_gl_proc(const char *name) {
    return dlsym(RTLD_DEFAULT, name);   /* iOS links OpenGLES statically */
}

void cui__plat_gl_swap(cui_app *app) {
    CUIIOSPlat *p = cui__ios_p(app);
    if (p.gl && !cui__ios_paused) [p.gl presentRenderbuffer:GL_RENDERBUFFER];
}

void cui__plat_gl_release(cui_app *app) {
    CUIIOSPlat *p = cui__ios_p(app);
    CUIIOSView *v = p.view;
    if (v && v.framebuffer) {
        unsigned int fb = v.framebuffer, rb = v.renderbuffer;
        glDeleteFramebuffers(1, &fb);
        glDeleteRenderbuffers(1, &rb);
        v.framebuffer = v.renderbuffer = 0;
    }
    if (p.gl && [EAGLContext currentContext] == p.gl) [EAGLContext setCurrentContext:nil];
    p.gl = nil;
}

/* ---- software renderer: BGRA buffer -> CGImage -> layer ---- */

void cui__plat_present(cui_app *app, const void *bgra, int w, int h, int stride) {
    CUIIOSPlat *p = cui__ios_p(app);
    if (!p.view) return;
    @autoreleasepool {
        CGColorSpaceRef cs = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
        CGContextRef ctx = CGBitmapContextCreate((void *)bgra, (size_t)w, (size_t)h, 8, (size_t)stride, cs,
                                                 kCGImageAlphaPremultipliedFirst | kCGBitmapByteOrder32Little);
        CGImageRef img = ctx ? CGBitmapContextCreateImage(ctx) : NULL;
        /* layer updates belong on the main thread; the image is retained
         * until the queued block has copied the reference into the layer */
        dispatch_async(dispatch_get_main_queue(), ^{
            [CATransaction begin];
            [CATransaction setDisableActions:YES];
            p.view.layer.contents = (__bridge id)img;
            p.view.layer.contentsScale = p.window.screen ? p.window.screen.scale : [UIScreen mainScreen].scale;
            [CATransaction commit];
            if (img) CGImageRelease(img);
        });
        if (ctx) CGContextRelease(ctx);
        CGColorSpaceRelease(cs);
    }
}

bool cui__plat_present_part(cui_app *app, const void *bgra, int w, int h, int stride, int x, int y, int pw, int ph) {
    (void)app; (void)bgra; (void)w; (void)h; (void)stride; (void)x; (void)y; (void)pw; (void)ph;
    return false;   /* the whole buffer is shown each time */
}

/* ---- metrics, title, native handle ---- */

/* the allocated drawable must match the laid-out view size × scale every
 * frame: gl_create can run at a provisional size on a cold start (before the
 * real window bounds are known), rotation changes bounds later, and the
 * relayout event may already be consumed when the size is read — so the
 * re-check must not fire only once. Reallocation is idempotent when the
 * sizes match. Runs on the app thread with the EAGL context current. */
static void cui__ios_fb_resize(CUIIOSPlat *p) {
    CUIIOSView *v = p.view;
    CAEAGLLayer *layer = (CAEAGLLayer *)v.layer;
    if (![layer isKindOfClass:[CAEAGLLayer class]]) return;   /* simulator fallback */
    CGFloat sc = p.window.screen ? p.window.screen.scale : [UIScreen mainScreen].scale;
    layer.contentsScale = sc;
    /* explicit transaction: renderbufferStorage from a non-main thread warns
     * when it lands in an implicit one */
    [CATransaction begin];
    glBindFramebuffer(GL_FRAMEBUFFER, v.framebuffer);
    glBindRenderbuffer(GL_RENDERBUFFER, v.renderbuffer);
    [p.gl renderbufferStorage:GL_RENDERBUFFER fromDrawable:layer];
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, v.renderbuffer);
    [CATransaction commit];
    GLint rbw = 0, rbh = 0;
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &rbw);
    glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &rbh);
    v.fb_width = (int)rbw;
    v.fb_height = (int)rbh;
}

void cui__plat_metrics(cui_app *app, float *w, float *h, float *scale, int *fb_w, int *fb_h) {
    CUIIOSPlat *p = cui__ios_p(app);
    CUIIOSView *v = p.view;
    if (v && v.framebuffer && p.gl && v.lay_w > 0 && v.lay_h > 0) {
        CGFloat sc = p.window.screen ? p.window.screen.scale : [UIScreen mainScreen].scale;
        int want_w = (int)(v.lay_w * sc + 0.5);
        int want_h = (int)(v.lay_h * sc + 0.5);
        if (want_w != v.fb_width || want_h != v.fb_height) {
            cui__ios_fb_resize(p);
        }
    }
    CGRect b = v ? v.bounds : [UIScreen mainScreen].bounds;
    float s = (float)(p.window.screen ? p.window.screen.scale : [UIScreen mainScreen].scale);
    const char *env = getenv("CUI_SCALE");
    if (env) { float e = (float)atof(env); if (e > 0.25f && e < 8) s = e; }
    *w = (float)b.size.width;
    *h = (float)b.size.height;
    *scale = s;
    *fb_w = (int)(b.size.width * s + 0.5);
    *fb_h = (int)(b.size.height * s + 0.5);
}

void cui__plat_set_title(cui_app *app, const char *title) { (void)app; (void)title; }
void cui__plat_set_size(cui_app *app, int w, int h) { (void)app; (void)w; (void)h; }
void cui__plat_show(cui_app *app) { (void)app; }   /* the window is up before the app thread starts */
void *cui__plat_native(cui_app *app) { return (__bridge void *)cui__ios_p(app).window; }

/* one fullscreen window: no window management, nothing to change or report */
void cui__plat_maximize(cui_app *app) { (void)app; }
void cui__plat_minimize(cui_app *app) { (void)app; }
void cui__plat_restore(cui_app *app) { (void)app; }
void cui__plat_set_position(cui_app *app, int x, int y) { (void)app; (void)x; (void)y; }

cui_window_state cui__plat_window_state(cui_app *app) {
    (void)app;
    return CUI_WINDOW_NORMAL;
}

void cui__plat_placement(cui_app *app, cui_window_placement *out) {
    CUIIOSPlat *p = cui__ios_p(app);
    CGRect b = p.view ? p.view.bounds : [UIScreen mainScreen].bounds;
    out->x = 0;
    out->y = 0;
    out->width = (int)(b.size.width + 0.5);
    out->height = (int)(b.size.height + 0.5);
    out->state = CUI_WINDOW_NORMAL;
    out->has_position = false;
}

double cui__plat_refresh_hz(cui_app *app) {
    (void)app;
    return (double)[UIScreen mainScreen].maximumFramesPerSecond;
}

static void cui__ios_text_input_rect(void *user, cui_rect caret) {
    (void)caret;
    /* show the soft keyboard when a text edit wants a caret and the field is
     * not already first responder; the latch is re-armed by the text-start
     * callback so a dismissed keyboard can come back in a later session */
    CUIIOSPlat *p = cui__ios_p((cui_app *)user);
    if (p.kb_shown) return;
    p.kb_shown = YES;
    UITextField *f = p.field;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!f.isFirstResponder) [f becomeFirstResponder];
        else p.kb_shown = NO;   /* already up: allow a later re-request */
    });
}

/* ---- wait: give the app thread's time to the OS, then drain pending input ---- */

void cui__plat_wait(cui_app *app, double timeout) {
    struct timespec ts;
    bool timed = timeout > 0;
    if (timed) {
        clock_gettime(CLOCK_REALTIME, &ts);
        ts.tv_sec += (time_t)timeout;
        ts.tv_nsec += (long)((timeout - (double)(time_t)timeout) * 1e9);
        if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }
    }
    pthread_mutex_lock(&cui__ios_lock);
    /* events can land between the last drain and this wait: only sleep
     * while the queue is actually empty, and re-check after each wakeup */
    while (timeout < 0 && !cui__ios_head) pthread_cond_wait(&cui__ios_wake, &cui__ios_lock);
    if (timed) {
        while (timeout > 0 && !cui__ios_head) {
            if (pthread_cond_timedwait(&cui__ios_wake, &cui__ios_lock, &ts) == ETIMEDOUT) break;
        }
    }
    pthread_mutex_unlock(&cui__ios_lock);
    cui__ios_drain(app->ui);
}

/* ---- init / shutdown ---- */

bool cui__plat_init(cui_app *app) {
    /* UIApplicationMain runs on the main thread and builds the window; wait
     * for the delegate to have set it up, then adopt the platform object. */
    CUIIOSPlat *p = nil;
    for (int i = 0; i < 500 && !p; i++) {   /* up to ~5s */
        @autoreleasepool {
            p = (CUIIOSPlat *)cui__ios_plat;
            if (!p) usleep(10000);
        }
    }
    if (!p) return false;
    p.app = app;
    app->plat = (__bridge_retained void *)p;
    cui_platform_iface pi;
    memset(&pi, 0, sizeof pi);
    pi.user = app;
    pi.set_text_input_rect = cui__ios_text_input_rect;
    cui_set_platform(app->ui, &pi);
    return true;
}
void cui__plat_shutdown(cui_app *app) {
    if (!app->plat) return;
    CUIIOSPlat *p = (__bridge_transfer CUIIOSPlat *)app->plat;
    app->plat = NULL;
    cui__plat_gl_release(app);
    dispatch_async(dispatch_get_main_queue(), ^{
        p.window.hidden = YES;
        p.window = nil;
        p.view = nil;
        p.field = nil;
    });
}

#pragma clang diagnostic pop
