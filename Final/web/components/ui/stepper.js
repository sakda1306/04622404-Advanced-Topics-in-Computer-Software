"use client";

import { createContext, useContext, useState } from "react";

// Stepper primitives (horizontal or vertical): Stepper > StepperNav > StepperItem >
// StepperTrigger > StepperIndicator + StepperTitle, with StepperSeparator between
// items and optional StepperPanel > StepperContent. Every part carries data-state
// (completed | active | inactive) so callers can style each state with Tailwind
// data-[state=...] variants. Colours use the brand tokens in app/globals.css.

const cn = (...classes) => classes.filter(Boolean).join(" ");

const StepperContext = createContext(null);
const StepItemContext = createContext(null);

export function useStepper() {
  const ctx = useContext(StepperContext);
  if (!ctx) throw new Error("useStepper must be used within a Stepper");
  return ctx;
}

export function useStepItem() {
  const ctx = useContext(StepItemContext);
  if (!ctx) throw new Error("useStepItem must be used within a StepperItem");
  return ctx;
}

/**
 * Root. Uncontrolled with `defaultValue`, or controlled with `value` + `onValueChange`.
 * `indicators` replaces the indicator content per state, e.g. { completed: <CheckIcon /> }.
 */
export function Stepper({
  defaultValue = 1,
  value,
  onValueChange,
  orientation = "horizontal",
  indicators = {},
  className,
  children,
  ...props
}) {
  const [inner, setInner] = useState(defaultValue);
  const activeStep = value ?? inner;

  const setActiveStep = (step) => {
    if (value === undefined) setInner(step);
    onValueChange?.(step);
  };

  return (
    <StepperContext.Provider value={{ activeStep, setActiveStep, orientation, indicators }}>
      <div data-slot="stepper" data-orientation={orientation} className={cn("w-full", className)} {...props}>
        {children}
      </div>
    </StepperContext.Provider>
  );
}

export function StepperNav({ className, children, ...props }) {
  const { activeStep, orientation } = useStepper();
  return (
    <nav
      data-slot="stepper-nav"
      data-state={activeStep}
      data-orientation={orientation}
      className={cn(
        "group/stepper-nav inline-flex data-[orientation=horizontal]:w-full data-[orientation=horizontal]:flex-row data-[orientation=vertical]:flex-col",
        className,
      )}
      {...props}
    >
      <ol role="list" className="contents">
        {children}
      </ol>
    </nav>
  );
}

export function StepperItem({ step, completed = false, disabled = false, className, children, ...props }) {
  const { activeStep } = useStepper();
  const state = completed || step < activeStep ? "completed" : step === activeStep ? "active" : "inactive";

  return (
    <StepItemContext.Provider value={{ step, state, isDisabled: disabled }}>
      <li
        data-slot="stepper-item"
        data-state={state}
        className={cn(
          "group/step flex items-center justify-center group-data-[orientation=horizontal]/stepper-nav:flex-row group-data-[orientation=vertical]/stepper-nav:flex-col",
          className,
        )}
        {...props}
      >
        {children}
      </li>
    </StepItemContext.Provider>
  );
}

// Keys that move focus between triggers: the arrows along the orientation only,
// so the cross-axis arrows stay free for the page (e.g. /present's chapter keys).
const NAV_KEYS = {
  horizontal: ["ArrowRight", "ArrowLeft", "Home", "End"],
  vertical: ["ArrowDown", "ArrowUp", "Home", "End"],
};

/** Moves focus between the triggers of the same nav with the arrow, Home and End keys. */
function moveFocus(current, key) {
  const nav = current.closest('[data-slot="stepper-nav"]');
  if (!nav) return;
  const triggers = [...nav.querySelectorAll('[data-slot="stepper-trigger"]:not(:disabled)')];
  const i = triggers.indexOf(current);
  const n = triggers.length;
  const target = {
    ArrowDown: triggers[(i + 1) % n],
    ArrowRight: triggers[(i + 1) % n],
    ArrowUp: triggers[(i - 1 + n) % n],
    ArrowLeft: triggers[(i - 1 + n) % n],
    Home: triggers[0],
    End: triggers[n - 1],
  }[key];
  target?.focus();
}

export function StepperTrigger({ className, children, onClick, ...props }) {
  const { activeStep, setActiveStep, orientation } = useStepper();
  const { step, state, isDisabled } = useStepItem();
  const isActive = activeStep === step;

  return (
    <button
      type="button"
      data-slot="stepper-trigger"
      data-state={state}
      aria-current={isActive ? "step" : undefined}
      disabled={isDisabled}
      className={cn(
        "inline-flex cursor-pointer items-center gap-3 rounded-full outline-none focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-60",
        className,
      )}
      onClick={(e) => {
        setActiveStep(step);
        onClick?.(e);
      }}
      onKeyDown={(e) => {
        if (NAV_KEYS[orientation].includes(e.key)) {
          e.preventDefault();
          moveFocus(e.currentTarget, e.key);
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}

export function StepperIndicator({ className, children }) {
  const { state } = useStepItem();
  const { indicators } = useStepper();
  const custom = indicators[state];

  return (
    <span
      data-slot="stepper-indicator"
      data-state={state}
      className={cn(
        "tabular relative flex size-6 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-surface text-tiny font-semibold text-text-muted transition-colors duration-200",
        "data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-on-primary",
        "data-[state=completed]:border-success data-[state=completed]:bg-success data-[state=completed]:text-white",
        className,
      )}
    >
      {custom ?? children}
    </span>
  );
}

export function StepperSeparator({ className }) {
  const { state } = useStepItem();
  return (
    <span
      data-slot="stepper-separator"
      data-state={state}
      aria-hidden="true"
      className={cn(
        "m-0.5 rounded-full bg-border transition-colors duration-200 group-data-[orientation=horizontal]/stepper-nav:h-0.5 group-data-[orientation=horizontal]/stepper-nav:flex-1 group-data-[orientation=vertical]/stepper-nav:h-12 group-data-[orientation=vertical]/stepper-nav:w-0.5",
        className,
      )}
    />
  );
}

export function StepperTitle({ className, children }) {
  const { state } = useStepItem();
  return (
    <span data-slot="stepper-title" data-state={state} className={cn("block text-small leading-5 font-medium", className)}>
      {children}
    </span>
  );
}

export function StepperDescription({ className, children }) {
  const { state } = useStepItem();
  return (
    <span data-slot="stepper-description" data-state={state} className={cn("block text-small text-text-muted", className)}>
      {children}
    </span>
  );
}

export function StepperPanel({ className, children }) {
  const { activeStep } = useStepper();
  return (
    <div data-slot="stepper-panel" data-state={activeStep} className={cn("w-full", className)}>
      {children}
    </div>
  );
}

export function StepperContent({ value, forceMount = false, className, children }) {
  const { activeStep } = useStepper();
  const isActive = value === activeStep;
  if (!forceMount && !isActive) return null;
  return (
    <div data-slot="stepper-content" data-state={activeStep} className={cn("w-full", className)} hidden={!isActive}>
      {children}
    </div>
  );
}
