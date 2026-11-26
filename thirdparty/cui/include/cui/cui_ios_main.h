/* iOS apps: rename main so the backend (cui_app_ios.m) can own the process.
 *
 *   #include "cui_ios_main.h"
 *   int cui_ios_user_main(int argc, char **argv) { ... your main body ... }
 *
 * The backend starts your main on its own thread once UIApplicationMain has
 * built the window, so UIKit calls and cui_app_* calls never share a thread. */
#ifndef CUI_IOS_MAIN_H
#define CUI_IOS_MAIN_H

#ifndef CUI_PLATFORM_IOS
#define CUI_PLATFORM_IOS 1
#endif

#define main cui_ios_user_main

/* C++ apps: give the renamed entry C linkage so its symbol matches the one
 * the Objective-C backend calls (the macro alone would mangle it) */
#ifdef __cplusplus
extern "C" int cui_ios_user_main(int argc, char **argv);
#endif

#endif
