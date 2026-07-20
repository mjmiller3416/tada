import styles from "./Chip.module.css";

export type ChipTone =
  | "peach"
  | "berry"
  | "lavender"
  | "periwinkle"
  | "mint"
  | "coral"
  | "teal"
  | "neutral";

type ChipProps = {
  tone?: ChipTone;
  /** When provided the chip renders as a tappable button. */
  onClick?: () => void;
  className?: string;
  children: React.ReactNode;
};

/**
 * A fully-rounded pill for room tags, categories, and shortcuts.
 * Soft cheerful tints — colorful but never louder than the content.
 */
export default function Chip({
  tone = "neutral",
  onClick,
  className,
  children,
}: ChipProps) {
  const classes = [styles.chip, styles[tone], className ?? ""]
    .filter(Boolean)
    .join(" ");

  if (onClick) {
    return (
      <button type="button" className={`${classes} ${styles.tappable}`} onClick={onClick}>
        {children}
      </button>
    );
  }

  return <span className={classes}>{children}</span>;
}
