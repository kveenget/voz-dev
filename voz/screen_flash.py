"""
Destello verde alrededor de la ventana frontal — feedback visual de captura.
Se invoca como subprocess independiente; termina solo al acabar la animación.
"""
import sys

import objc
from AppKit import (
    NSApplication,
    NSApp,
    NSBackingStoreBuffered,
    NSColor,
    NSPanel,
    NSScreen,
    NSTimer,
)
from Foundation import NSObject
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
    kCGWindowListOptionOnScreenOnly,
)

BORDER = 3
CORNER = 16
FPS = 60
FADE_IN = 10
HOLD = 22
FADE_OUT = 12


def _front_ns_frame():
    sh = NSScreen.mainScreen().frame().size.height
    wins = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    for w in wins:
        if w.get("kCGWindowLayer", 99) != 0:
            continue
        b = w.get("kCGWindowBounds")
        if b and b["Width"] > 120 and b["Height"] > 80:
            ns_y = sh - b["Y"] - b["Height"]
            return b["X"], ns_y, b["Width"], b["Height"]
    return None


class _Animator(NSObject):
    def initWithPanel_(self, panel):
        self = objc.super(_Animator, self).init()
        self._panel = panel
        self._f = 0
        return self

    def tick_(self, timer):
        f = self._f
        total = FADE_IN + HOLD + FADE_OUT
        if f < FADE_IN:
            alpha = (f + 1) / FADE_IN
        elif f < FADE_IN + HOLD:
            alpha = 1.0
        else:
            r = f - FADE_IN - HOLD
            alpha = max(0.0, 1.0 - (r + 1) / FADE_OUT)

        self._panel.setAlphaValue_(alpha)
        self._f += 1

        if f >= total:
            timer.invalidate()
            self._panel.close()
            NSApp.stop_(None)


def main():
    NSApplication.sharedApplication()
    NSApp.setActivationPolicy_(1)  # Accessory — sin ícono en Dock

    frame = _front_ns_frame()
    if not frame:
        return

    x, y, w, h = frame
    pad = BORDER + 3

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        ((x - pad, y - pad), (w + pad * 2, h + pad * 2)),
        0,  # NSWindowStyleMaskBorderless
        NSBackingStoreBuffered,
        False,
    )
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setLevel_(2001)
    panel.setIgnoresMouseEvents_(True)
    panel.setHasShadow_(False)
    panel.setAlphaValue_(0.0)
    panel.makeKeyAndOrderFront_(None)

    v = panel.contentView()
    v.setWantsLayer_(True)
    layer = v.layer()
    layer.setCornerRadius_(float(CORNER))
    layer.setBorderWidth_(float(BORDER))
    layer.setBorderColor_(
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.133, 0.773, 0.369, 1.0).CGColor()
    )

    anim = _Animator.alloc().initWithPanel_(panel)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / FPS, anim, "tick:", None, True
    )
    NSApp.run()


if __name__ == "__main__":
    main()
