import gsap from 'gsap';
import { useEffect, useRef } from 'react';

import { useGSAP } from '@gsap/react';

gsap.registerPlugin();

// ─── Pupil ───────────────────────────────────────────────────────────────────

interface PupilProps {
    size?: number;
    maxDistance?: number;
    pupilColor?: string;
}

const Pupil = ({ size = 12, maxDistance = 5, pupilColor = 'black' }: PupilProps) => {
    return (
        <div
            data-max-distance={maxDistance}
            className="pupil"
            style={{
                width: size,
                height: size,
                borderRadius: '50%',
                backgroundColor: pupilColor,
                willChange: 'transform',
            }}
        />
    );
};

// ─── EyeBall ──────────────────────────────────────────────────────────────────

interface EyeBallProps {
    size?: number;
    pupilSize?: number;
    maxDistance?: number;
    eyeColor?: string;
    pupilColor?: string;
}

const EyeBall = ({
    size = 48,
    pupilSize = 16,
    maxDistance = 10,
    eyeColor = 'white',
    pupilColor = 'black',
}: EyeBallProps) => {
    return (
        <div
            className="eyeball"
            data-max-distance={maxDistance}
            style={{
                width: size,
                height: size,
                borderRadius: '50%',
                backgroundColor: eyeColor,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                willChange: 'height',
            }}
        >
            <div
                className="eyeball-pupil"
                style={{
                    width: pupilSize,
                    height: pupilSize,
                    borderRadius: '50%',
                    backgroundColor: pupilColor,
                    willChange: 'transform',
                }}
            />
        </div>
    );
};

// ─── AnimatedCharacters ───────────────────────────────────────────────────────

export interface AnimatedCharactersProps {
    isTyping?: boolean;
    showPassword?: boolean;
    passwordLength?: number;
}

export function AnimatedCharacters({
    isTyping = false,
    showPassword = false,
    passwordLength = 0,
}: AnimatedCharactersProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const mouseRef = useRef({ x: 0, y: 0 });
    const rafIdRef = useRef(0);

    const purpleRef = useRef<HTMLDivElement>(null);
    const blackRef = useRef<HTMLDivElement>(null);
    const yellowRef = useRef<HTMLDivElement>(null);
    const orangeRef = useRef<HTMLDivElement>(null);

    const purpleFaceRef = useRef<HTMLDivElement>(null);
    const blackFaceRef = useRef<HTMLDivElement>(null);
    const yellowFaceRef = useRef<HTMLDivElement>(null);
    const orangeFaceRef = useRef<HTMLDivElement>(null);

    const yellowMouthRef = useRef<HTMLDivElement>(null);

    const purpleBlinkTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
    const blackBlinkTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
    const purplePeekTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

    const isHidingPassword = passwordLength > 0 && !showPassword;
    const isShowingPassword = passwordLength > 0 && showPassword;

    const isLookingRef = useRef(false);
    const lookingTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

    const stateRef = useRef({ isTyping, isHidingPassword, isShowingPassword, isLooking: false });
    stateRef.current = {
        isTyping,
        isHidingPassword,
        isShowingPassword,
        isLooking: isLookingRef.current,
    };

    const { contextSafe } = useGSAP(
        () => {
            gsap.set('.pupil', { x: 0, y: 0 });
            gsap.set('.eyeball-pupil', { x: 0, y: 0 });
        },
        { scope: containerRef }
    );

    const quickToRef = useRef<{
        purpleSkew: gsap.QuickToFunc;
        blackSkew: gsap.QuickToFunc;
        orangeSkew: gsap.QuickToFunc;
        yellowSkew: gsap.QuickToFunc;
        purpleX: gsap.QuickToFunc;
        blackX: gsap.QuickToFunc;
        purpleHeight: gsap.QuickToFunc;
        purpleFaceLeft: gsap.QuickToFunc;
        purpleFaceTop: gsap.QuickToFunc;
        blackFaceLeft: gsap.QuickToFunc;
        blackFaceTop: gsap.QuickToFunc;
        orangeFaceX: gsap.QuickToFunc;
        orangeFaceY: gsap.QuickToFunc;
        yellowFaceX: gsap.QuickToFunc;
        yellowFaceY: gsap.QuickToFunc;
        mouthX: gsap.QuickToFunc;
        mouthY: gsap.QuickToFunc;
    } | null>(null);

    useEffect(() => {
        if (
            !purpleRef.current ||
            !blackRef.current ||
            !orangeRef.current ||
            !yellowRef.current ||
            !purpleFaceRef.current ||
            !blackFaceRef.current ||
            !orangeFaceRef.current ||
            !yellowFaceRef.current ||
            !yellowMouthRef.current
        )
            return;

        const qt = {
            purpleSkew: gsap.quickTo(purpleRef.current, 'skewX', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            blackSkew: gsap.quickTo(blackRef.current, 'skewX', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            orangeSkew: gsap.quickTo(orangeRef.current, 'skewX', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            yellowSkew: gsap.quickTo(yellowRef.current, 'skewX', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            purpleX: gsap.quickTo(purpleRef.current, 'x', { duration: 0.3, ease: 'power2.out' }),
            blackX: gsap.quickTo(blackRef.current, 'x', { duration: 0.3, ease: 'power2.out' }),
            purpleHeight: gsap.quickTo(purpleRef.current, 'height', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            purpleFaceLeft: gsap.quickTo(purpleFaceRef.current, 'left', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            purpleFaceTop: gsap.quickTo(purpleFaceRef.current, 'top', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            blackFaceLeft: gsap.quickTo(blackFaceRef.current, 'left', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            blackFaceTop: gsap.quickTo(blackFaceRef.current, 'top', {
                duration: 0.3,
                ease: 'power2.out',
            }),
            orangeFaceX: gsap.quickTo(orangeFaceRef.current, 'x', {
                duration: 0.2,
                ease: 'power2.out',
            }),
            orangeFaceY: gsap.quickTo(orangeFaceRef.current, 'y', {
                duration: 0.2,
                ease: 'power2.out',
            }),
            yellowFaceX: gsap.quickTo(yellowFaceRef.current, 'x', {
                duration: 0.2,
                ease: 'power2.out',
            }),
            yellowFaceY: gsap.quickTo(yellowFaceRef.current, 'y', {
                duration: 0.2,
                ease: 'power2.out',
            }),
            mouthX: gsap.quickTo(yellowMouthRef.current, 'x', {
                duration: 0.2,
                ease: 'power2.out',
            }),
            mouthY: gsap.quickTo(yellowMouthRef.current, 'y', {
                duration: 0.2,
                ease: 'power2.out',
            }),
        };
        quickToRef.current = qt;

        const calcPos = (el: HTMLElement) => {
            const rect = el.getBoundingClientRect();
            const cx = rect.left + rect.width / 2;
            const cy = rect.top + rect.height / 3;
            const dx = mouseRef.current.x - cx;
            const dy = mouseRef.current.y - cy;
            return {
                faceX: Math.max(-15, Math.min(15, dx / 20)),
                faceY: Math.max(-10, Math.min(10, dy / 30)),
                bodySkew: Math.max(-6, Math.min(6, -dx / 120)),
            };
        };

        const calcEyePos = (el: HTMLElement, maxDist: number) => {
            const r = el.getBoundingClientRect();
            const cx = r.left + r.width / 2;
            const cy = r.top + r.height / 2;
            const dx = mouseRef.current.x - cx;
            const dy = mouseRef.current.y - cy;
            const dist = Math.min(Math.sqrt(dx ** 2 + dy ** 2), maxDist);
            const angle = Math.atan2(dy, dx);
            return { x: Math.cos(angle) * dist, y: Math.sin(angle) * dist };
        };

        const tick = () => {
            const container = containerRef.current;
            if (!container) return;

            const {
                isTyping: typing,
                isHidingPassword: hiding,
                isShowingPassword: showing,
                isLooking: looking,
            } = stateRef.current;

            if (purpleRef.current && !showing) {
                const pp = calcPos(purpleRef.current);
                if (typing || hiding) {
                    qt.purpleSkew(pp.bodySkew - 12);
                    qt.purpleX(40);
                    qt.purpleHeight(440);
                } else {
                    qt.purpleSkew(pp.bodySkew);
                    qt.purpleX(0);
                    qt.purpleHeight(400);
                }
            }

            if (blackRef.current && !showing) {
                const bp = calcPos(blackRef.current);
                if (looking) {
                    qt.blackSkew(bp.bodySkew * 1.5 + 10);
                    qt.blackX(20);
                } else if (typing || hiding) {
                    qt.blackSkew(bp.bodySkew * 1.5);
                    qt.blackX(0);
                } else {
                    qt.blackSkew(bp.bodySkew);
                    qt.blackX(0);
                }
            }

            if (orangeRef.current && !showing) {
                const op = calcPos(orangeRef.current);
                qt.orangeSkew(op.bodySkew);
            }

            if (yellowRef.current && !showing) {
                const yp = calcPos(yellowRef.current);
                qt.yellowSkew(yp.bodySkew);
            }

            if (purpleRef.current && !showing && !looking) {
                const pp = calcPos(purpleRef.current);
                const purpleFaceX = pp.faceX >= 0 ? Math.min(25, pp.faceX * 1.5) : pp.faceX;
                qt.purpleFaceLeft(45 + purpleFaceX);
                qt.purpleFaceTop(40 + pp.faceY);
            }

            if (blackRef.current && !showing && !looking) {
                const bp = calcPos(blackRef.current);
                qt.blackFaceLeft(26 + bp.faceX);
                qt.blackFaceTop(32 + bp.faceY);
            }

            if (orangeRef.current && !showing) {
                const op = calcPos(orangeRef.current);
                qt.orangeFaceX(op.faceX);
                qt.orangeFaceY(op.faceY);
            }

            if (yellowRef.current && !showing) {
                const yp = calcPos(yellowRef.current);
                qt.yellowFaceX(yp.faceX);
                qt.yellowFaceY(yp.faceY);
            }

            if (yellowRef.current && !showing) {
                const yp = calcPos(yellowRef.current);
                qt.mouthX(yp.faceX);
                qt.mouthY(yp.faceY);
            }

            if (!showing) {
                const allPupils = container.querySelectorAll('.pupil');
                allPupils.forEach((p) => {
                    const el = p as HTMLElement;
                    const maxDist = Number(el.dataset.maxDistance) || 5;
                    const ePos = calcEyePos(el, maxDist);
                    gsap.set(el, { x: ePos.x, y: ePos.y });
                });

                if (!looking) {
                    const allEyeballs = container.querySelectorAll('.eyeball');
                    allEyeballs.forEach((eb) => {
                        const el = eb as HTMLElement;
                        const maxDist = Number(el.dataset.maxDistance) || 10;
                        const pupil = el.querySelector('.eyeball-pupil') as HTMLElement;
                        if (!pupil) return;
                        const ePos = calcEyePos(el, maxDist);
                        gsap.set(pupil, { x: ePos.x, y: ePos.y });
                    });
                }
            }

            rafIdRef.current = requestAnimationFrame(tick);
        };

        const onMove = (e: MouseEvent) => {
            mouseRef.current = { x: e.clientX, y: e.clientY };
        };

        window.addEventListener('mousemove', onMove, { passive: true });
        rafIdRef.current = requestAnimationFrame(tick);

        return () => {
            window.removeEventListener('mousemove', onMove);
            cancelAnimationFrame(rafIdRef.current);
        };
    }, []);

    useEffect(() => {
        const purpleEyeballs = purpleRef.current?.querySelectorAll('.eyeball');
        if (!purpleEyeballs?.length) return;

        const scheduleBlink = () => {
            purpleBlinkTimerRef.current = setTimeout(
                () => {
                    purpleEyeballs.forEach((el) => {
                        gsap.to(el, { height: 2, duration: 0.08, ease: 'power2.in' });
                    });
                    setTimeout(() => {
                        purpleEyeballs.forEach((el) => {
                            const size =
                                Number((el as HTMLElement).style.width.replace('px', '')) || 18;
                            gsap.to(el, { height: size, duration: 0.08, ease: 'power2.out' });
                        });
                        scheduleBlink();
                    }, 150);
                },
                Math.random() * 4000 + 3000
            );
        };

        scheduleBlink();
        return () => clearTimeout(purpleBlinkTimerRef.current);
    }, []);

    useEffect(() => {
        const blackEyeballs = blackRef.current?.querySelectorAll('.eyeball');
        if (!blackEyeballs?.length) return;

        const scheduleBlink = () => {
            blackBlinkTimerRef.current = setTimeout(
                () => {
                    blackEyeballs.forEach((el) => {
                        gsap.to(el, { height: 2, duration: 0.08, ease: 'power2.in' });
                    });
                    setTimeout(() => {
                        blackEyeballs.forEach((el) => {
                            const size =
                                Number((el as HTMLElement).style.width.replace('px', '')) || 16;
                            gsap.to(el, { height: size, duration: 0.08, ease: 'power2.out' });
                        });
                        scheduleBlink();
                    }, 150);
                },
                Math.random() * 4000 + 3000
            );
        };

        scheduleBlink();
        return () => clearTimeout(blackBlinkTimerRef.current);
    }, []);

    const applyLookAtEachOther = contextSafe(() => {
        const qt = quickToRef.current;
        if (qt) {
            qt.purpleFaceLeft(55);
            qt.purpleFaceTop(65);
            qt.blackFaceLeft(32);
            qt.blackFaceTop(12);
        }
        purpleRef.current?.querySelectorAll('.eyeball-pupil').forEach((p) => {
            gsap.to(p, { x: 3, y: 4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
        blackRef.current?.querySelectorAll('.eyeball-pupil').forEach((p) => {
            gsap.to(p, { x: 0, y: -4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
    });

    const applyHidingPassword = contextSafe(() => {
        const qt = quickToRef.current;
        if (qt) {
            qt.purpleFaceLeft(55);
            qt.purpleFaceTop(65);
        }
    });

    const applyShowPassword = contextSafe(() => {
        const qt = quickToRef.current;
        if (qt) {
            qt.purpleSkew(0);
            qt.blackSkew(0);
            qt.orangeSkew(0);
            qt.yellowSkew(0);
            qt.purpleX(0);
            qt.blackX(0);
            qt.purpleHeight(400);

            qt.purpleFaceLeft(20);
            qt.purpleFaceTop(35);
            qt.blackFaceLeft(10);
            qt.blackFaceTop(28);
            qt.orangeFaceX(50 - 82);
            qt.orangeFaceY(85 - 90);
            qt.yellowFaceX(20 - 52);
            qt.yellowFaceY(35 - 40);
            qt.mouthX(10 - 40);
            qt.mouthY(0);
        }

        purpleRef.current?.querySelectorAll('.eyeball-pupil').forEach((p) => {
            gsap.to(p, { x: -4, y: -4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
        blackRef.current?.querySelectorAll('.eyeball-pupil').forEach((p) => {
            gsap.to(p, { x: -4, y: -4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
        orangeRef.current?.querySelectorAll('.pupil').forEach((p) => {
            gsap.to(p, { x: -5, y: -4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
        yellowRef.current?.querySelectorAll('.pupil').forEach((p) => {
            gsap.to(p, { x: -5, y: -4, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
        });
    });

    useEffect(() => {
        if (!isShowingPassword || passwordLength <= 0) {
            clearTimeout(purplePeekTimerRef.current);
            return;
        }

        const purpleEyePupils = purpleRef.current?.querySelectorAll('.eyeball-pupil');
        if (!purpleEyePupils?.length) return;

        const schedulePeek = () => {
            purplePeekTimerRef.current = setTimeout(
                () => {
                    purpleEyePupils.forEach((p) => {
                        gsap.to(p, {
                            x: 4,
                            y: 5,
                            duration: 0.3,
                            ease: 'power2.out',
                            overwrite: 'auto',
                        });
                    });
                    const qt = quickToRef.current;
                    if (qt) {
                        qt.purpleFaceLeft(20);
                        qt.purpleFaceTop(35);
                    }

                    setTimeout(() => {
                        purpleEyePupils.forEach((p) => {
                            gsap.to(p, {
                                x: -4,
                                y: -4,
                                duration: 0.3,
                                ease: 'power2.out',
                                overwrite: 'auto',
                            });
                        });
                        schedulePeek();
                    }, 800);
                },
                Math.random() * 3000 + 2000
            );
        };

        schedulePeek();
        return () => clearTimeout(purplePeekTimerRef.current);
    }, [isShowingPassword, passwordLength]);

    useEffect(() => {
        if (isTyping && !isShowingPassword) {
            isLookingRef.current = true;
            stateRef.current.isLooking = true;
            applyLookAtEachOther();

            clearTimeout(lookingTimerRef.current);
            lookingTimerRef.current = setTimeout(() => {
                isLookingRef.current = false;
                stateRef.current.isLooking = false;
                purpleRef.current?.querySelectorAll('.eyeball-pupil').forEach((p) => {
                    gsap.killTweensOf(p);
                });
            }, 800);
        } else {
            clearTimeout(lookingTimerRef.current);
            isLookingRef.current = false;
            stateRef.current.isLooking = false;
        }
        return () => clearTimeout(lookingTimerRef.current);
    }, [isTyping, isShowingPassword]);

    useEffect(() => {
        if (isShowingPassword) {
            applyShowPassword();
        } else if (isHidingPassword) {
            applyHidingPassword();
        }
    }, [isHidingPassword, isShowingPassword]);

    return (
        <div ref={containerRef} style={{ position: 'relative', width: 550, height: 400 }}>
            <div
                ref={purpleRef}
                style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 70,
                    width: 180,
                    height: 400,
                    backgroundColor: '#6C3FF5',
                    borderRadius: '10px 10px 0 0',
                    zIndex: 1,
                    transformOrigin: 'bottom center',
                    willChange: 'transform',
                }}
            >
                <div
                    ref={purpleFaceRef}
                    style={{
                        position: 'absolute',
                        display: 'flex',
                        gap: 32,
                        left: 45,
                        top: 40,
                    }}
                >
                    <EyeBall
                        size={18}
                        pupilSize={7}
                        maxDistance={5}
                        eyeColor="white"
                        pupilColor="#2D2D2D"
                    />
                    <EyeBall
                        size={18}
                        pupilSize={7}
                        maxDistance={5}
                        eyeColor="white"
                        pupilColor="#2D2D2D"
                    />
                </div>
            </div>

            <div
                ref={blackRef}
                style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 240,
                    width: 120,
                    height: 310,
                    backgroundColor: '#2D2D2D',
                    borderRadius: '8px 8px 0 0',
                    zIndex: 2,
                    transformOrigin: 'bottom center',
                    willChange: 'transform',
                }}
            >
                <div
                    ref={blackFaceRef}
                    style={{
                        position: 'absolute',
                        display: 'flex',
                        gap: 24,
                        left: 26,
                        top: 32,
                    }}
                >
                    <EyeBall
                        size={16}
                        pupilSize={6}
                        maxDistance={4}
                        eyeColor="white"
                        pupilColor="#2D2D2D"
                    />
                    <EyeBall
                        size={16}
                        pupilSize={6}
                        maxDistance={4}
                        eyeColor="white"
                        pupilColor="#2D2D2D"
                    />
                </div>
            </div>

            <div
                ref={orangeRef}
                style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    width: 240,
                    height: 200,
                    backgroundColor: '#FF9B6B',
                    borderRadius: '120px 120px 0 0',
                    zIndex: 3,
                    transformOrigin: 'bottom center',
                    willChange: 'transform',
                }}
            >
                <div
                    ref={orangeFaceRef}
                    style={{
                        position: 'absolute',
                        display: 'flex',
                        gap: 32,
                        left: 82,
                        top: 90,
                    }}
                >
                    <Pupil size={12} maxDistance={5} pupilColor="#2D2D2D" />
                    <Pupil size={12} maxDistance={5} pupilColor="#2D2D2D" />
                </div>
            </div>

            <div
                ref={yellowRef}
                style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 310,
                    width: 140,
                    height: 230,
                    backgroundColor: '#E8D754',
                    borderRadius: '70px 70px 0 0',
                    zIndex: 4,
                    transformOrigin: 'bottom center',
                    willChange: 'transform',
                }}
            >
                <div
                    ref={yellowFaceRef}
                    style={{
                        position: 'absolute',
                        display: 'flex',
                        gap: 24,
                        left: 52,
                        top: 40,
                    }}
                >
                    <Pupil size={12} maxDistance={5} pupilColor="#2D2D2D" />
                    <Pupil size={12} maxDistance={5} pupilColor="#2D2D2D" />
                </div>
                <div
                    ref={yellowMouthRef}
                    style={{
                        position: 'absolute',
                        width: 80,
                        height: 4,
                        backgroundColor: '#2D2D2D',
                        borderRadius: 9999,
                        left: 40,
                        top: 88,
                    }}
                />
            </div>
        </div>
    );
}
