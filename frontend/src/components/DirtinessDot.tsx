import type { Band } from "@/lib/api";
import { BAND_COLOR_VAR, BAND_LABEL } from "@/lib/decay";
import styles from "./DirtinessDot.module.css";

type DirtinessDotProps = {
  band: Band;
  /** Also render the warm band label next to the dot. */
  withLabel?: boolean;
};

/** The decay signal, rendered the same way everywhere: a small colored
 * dot (SPEC §4 bands), optionally with its warm label. */
export default function DirtinessDot({ band, withLabel = false }: DirtinessDotProps) {
  return (
    <span className={styles.wrap} title={BAND_LABEL[band]}>
      <span
        className={styles.dot}
        style={{ background: BAND_COLOR_VAR[band] }}
        aria-hidden="true"
      />
      {withLabel && <span className={styles.label}>{BAND_LABEL[band]}</span>}
    </span>
  );
}
