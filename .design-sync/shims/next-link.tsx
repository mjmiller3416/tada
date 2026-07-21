/**
 * design-sync shim for next/link. Outside the Next.js runtime a Link is an
 * anchor: router-only props are dropped and navigation is the browser's.
 * Aliased in via tsconfig.sync.json so Next's client internals (which
 * reference process.env.*) never enter the design-system bundle.
 */
import * as React from "react";

type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  prefetch?: boolean;
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
};

const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { href, prefetch, replace, scroll, shallow, children, ...rest },
  ref,
) {
  return (
    <a ref={ref} href={href} {...rest}>
      {children}
    </a>
  );
});

export default Link;
