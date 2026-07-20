import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "success" | "secondary" | "ghost";
export type ButtonSize = "md" | "lg";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  /**
   * primary   — coral, the main "go" action ("I have 15 minutes")
   * success   — teal, completion actions (the big Done button)
   * secondary — quiet surface + border, supporting actions
   * ghost     — text-only, the quietest ("Skip for now")
   */
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
};

export default function Button({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className,
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    styles[size],
    fullWidth ? styles.fullWidth : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return <button className={classes} {...rest} />;
}
