import { useEffect, useRef, useState } from "react";

/**
 * A dropdown that belongs to the sidebar.
 *
 * The native `<select>` is what the composer used, and it failed in three ways
 * that all read as "the control does not work":
 *
 * * its popup is drawn by the platform, outside the shadow root, so it is not
 *   centred on the trigger and can open off-screen when the sidebar is narrow;
 * * an option can only be a string, so a disabled one ("当前选区" without a
 *   selection) gave no reason and a model could not show what it can do;
 * * the closed trigger shows the selected label at the platform's font size,
 *   which does not match anything else in the panel.
 *
 * This renders inside the shadow tree, shows a second line for the reason or
 * capability, and opens *upwards* by default because the composer sits at the
 * bottom of the panel — a downward popup would be pushed off the viewport.
 */
export interface SelectOption {
  value: string;
  label: string;
  /** Second line: what this choice means, or why it is unavailable. */
  hint?: string;
  /** Short capability tag, e.g. "可读图". */
  badge?: string;
  disabled?: boolean;
  disabledReason?: string;
}

export function Select(props: {
  value: string;
  options: SelectOption[];
  onChange(value: string): void;
  /** Accessible name, also used as the tooltip. */
  label: string;
  placement?: "up" | "down";
  /** Narrow trigger used inside the composer. */
  compact?: boolean;
}): JSX.Element {
  const { value, options, onChange, label } = props;
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const current = options.find((option) => option.value === value);

  // The list is deliberately not a `<select>`: closing on an outside pointerdown
  // has to reach through the shadow boundary, which `composedPath()` does and
  // `event.target` does not (it is retargeted to the host element).
  useEffect(() => {
    if (!open) {
      return;
    }
    const onDown = (event: Event) => {
      const path = (event as Event & { composedPath?: () => EventTarget[] }).composedPath?.() || [];
      if (boxRef.current && !path.includes(boxRef.current)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Stop the sidebar's own Escape handler from also closing the panel
        // behind this one.
        event.stopPropagation();
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const pick = (option: SelectOption) => {
    if (option.disabled) {
      return;
    }
    setOpen(false);
    if (option.value !== value) {
      onChange(option.value);
    }
  };

  return (
    <div className={`pl-dd${props.compact ? " pl-dd--compact" : ""}`} ref={boxRef}>
      <button
        type="button"
        className={`pl-dd__trigger${open ? " active" : ""}`}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={label}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className="pl-dd__text">{current ? current.label : value || "未选择"}</span>
        <span className="pl-dd__caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open ? (
        <ul
          className={`pl-dd__list pl-dd__list--${props.placement || "down"}`}
          role="listbox"
          aria-label={label}
        >
          {options.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={`pl-dd__option${option.value === value ? " active" : ""}${
                  option.disabled ? " disabled" : ""
                }`}
                disabled={option.disabled}
                title={option.disabled ? option.disabledReason || option.hint : option.hint}
                onClick={() => pick(option)}
              >
                <span className="pl-dd__row">
                  <span className="pl-dd__label">{option.label}</span>
                  {option.badge ? <span className="pl-dd__badge">{option.badge}</span> : null}
                  {option.value === value ? (
                    <span className="pl-dd__check" aria-hidden="true">
                      ✓
                    </span>
                  ) : null}
                </span>
                {option.disabled && option.disabledReason ? (
                  <span className="pl-dd__hint">{option.disabledReason}</span>
                ) : option.hint ? (
                  <span className="pl-dd__hint">{option.hint}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Three or four mutually exclusive choices, all visible at once.
 *
 * Used for the context scope, which has exactly three values. A dropdown hid two
 * of them behind a click and could not explain why "当前选区" was unavailable;
 * here the reason is a tooltip on a control the user can see.
 */
export function Segmented(props: {
  value: string;
  options: { value: string; label: string; title?: string; disabled?: boolean }[];
  onChange(value: string): void;
  label: string;
}): JSX.Element {
  return (
    <div className="pl-seg" role="group" aria-label={props.label}>
      {props.options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`pl-seg__item${option.value === props.value ? " active" : ""}`}
          aria-pressed={option.value === props.value}
          disabled={option.disabled}
          title={option.title || option.label}
          onClick={() => {
            if (!option.disabled && option.value !== props.value) {
              props.onChange(option.value);
            }
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
