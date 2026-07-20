import styles from "./Card.module.css";

type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  padding?: "none" | "md" | "lg";
};

/** A soft, rounded surface — the basic building block for content blocks. */
export default function Card({
  padding = "md",
  className,
  ...rest
}: CardProps) {
  const classes = [
    styles.card,
    padding !== "none" ? styles[padding] : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return <div className={classes} {...rest} />;
}
