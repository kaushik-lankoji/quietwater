import { useEffect, useRef, type ReactNode } from "react";
import { cls } from "../format";
import { Icon } from "./Icon";

export function Sheet({
  open,
  title,
  meta,
  flush,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  meta?: ReactNode;
  flush?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.inert = !open;
  }, [open]);
  return (
    <aside ref={ref} className={cls("sheet glass", open && "open")} aria-label={title} aria-hidden={!open}>
      <header className="sheet-head">
        <div className="sheet-title-block">
          <h2 className="sheet-title">{title}</h2>
          {meta && <div className="sheet-meta">{meta}</div>}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label={`Close ${title}`}>
          <Icon name="close" size={20} />
        </button>
      </header>
      <div className={cls("sheet-body", flush && "flush")}>{children}</div>
    </aside>
  );
}
