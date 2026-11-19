/**
 * Whether a keydown in the composer should send the message.
 *
 * Getting this wrong is a very visible bug for anyone typing Chinese: pressing
 * Enter to *confirm an IME candidate* also fires a keydown with `key === "Enter"`,
 * and the old handler sent the half-finished sentence. The same event is used by
 * Japanese, Korean and Vietnamese input, so the check cannot be region-specific.
 *
 * Three signals are consulted because no single one is reliable across the Gecko
 * builds Zotero ships:
 *
 *  - `isComposing` on the native event (the standard);
 *  - `keyCode === 229`, which is what some builds report for "this key is being
 *    consumed by the IME";
 *  - our own composition-start/end tracking, because a keydown can arrive after
 *    `compositionend` on the same tick in some builds.
 */

export interface ComposerKeyEvent {
  key: string;
  shiftKey: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  /** `KeyboardEvent.isComposing`. */
  isComposing?: boolean;
  /** Deprecated but still the only signal in some builds. */
  keyCode?: number;
  /** Whether our compositionstart/compositionend tracker says a composition is open. */
  composing: boolean;
}

/** True when the keystroke is the IME confirming a candidate, not a send. */
export function isImeConfirmation(event: ComposerKeyEvent): boolean {
  if (event.composing) {
    return true;
  }
  if (event.isComposing) {
    return true;
  }
  // 229 is the "IME is processing this key" code. It is deprecated, but it is the
  // only thing older Gecko reports while a candidate window is open.
  return event.keyCode === 229;
}

/**
 * True when Enter should send. Shift+Enter inserts a newline, and a modifier
 * combination (Ctrl/Cmd/Alt+Enter) is left to the browser so it cannot
 * accidentally send while the user means something else.
 */
export function shouldSendOnEnter(event: ComposerKeyEvent): boolean {
  if (event.key !== "Enter" || event.shiftKey) {
    return false;
  }
  if (event.ctrlKey || event.metaKey || event.altKey) {
    return false;
  }
  return !isImeConfirmation(event);
}
