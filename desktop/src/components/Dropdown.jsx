import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function Dropdown({ value, onChange, options, ariaLabel, required = false, className = "" }) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuStyle, setMenuStyle] = useState(null);
  const rootRef = useRef(null);
  const menuRef = useRef(null);
  const listId = useId();
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const selected = options.find((option) => option.value === value) || options[0];

  function placeMenu() {
    const trigger = rootRef.current?.querySelector(".dropdown-trigger");
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUp = spaceBelow < 240 && rect.top > spaceBelow;
    setMenuStyle({
      position: "fixed",
      left: rect.left,
      width: rect.width,
      top: openUp ? "auto" : rect.bottom + 6,
      bottom: openUp ? window.innerHeight - rect.top + 6 : "auto",
      zIndex: 40,
    });
  }

  useEffect(() => {
    if (!open) return undefined;
    placeMenu();
    function onPointer(event) {
      if (rootRef.current?.contains(event.target) || menuRef.current?.contains(event.target)) return;
      setOpen(false);
    }
    function onLayout() {
      placeMenu();
    }
    document.addEventListener("mousedown", onPointer);
    window.addEventListener("resize", onLayout);
    window.addEventListener("scroll", onLayout, true);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      window.removeEventListener("resize", onLayout);
      window.removeEventListener("scroll", onLayout, true);
    };
  }, [open]);

  function choose(option) {
    onChange(option.value);
    setOpen(false);
  }

  function onKeyDown(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = event.key === "ArrowDown" ? 1 : -1;
      if (!open) {
        setActiveIndex(selectedIndex);
        setOpen(true);
        return;
      }
      setActiveIndex((current) => Math.max(0, Math.min(options.length - 1, current + next)));
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        setActiveIndex(selectedIndex);
        setOpen(true);
        return;
      }
      if (options[activeIndex]) choose(options[activeIndex]);
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const menu = open ? (
    <ul ref={menuRef} id={listId} className="dropdown-menu" role="listbox" style={menuStyle}>
      {options.map((option, index) => {
        const isSelected = option.value === value;
        return (
          <li key={`${option.value}-${index}`}>
            <button
              type="button"
              role="option"
              aria-selected={isSelected}
              className={`dropdown-option${index === activeIndex ? " active" : ""}${isSelected ? " selected" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(option)}
            >
              <span>{option.label}</span>
              {isSelected && <span className="dropdown-mark" aria-hidden="true" />}
            </button>
          </li>
        );
      })}
    </ul>
  ) : null;

  return (
    <div ref={rootRef} className={`dropdown${open ? " open" : ""} ${className}`.trim()}>
      <button
        type="button"
        className={`dropdown-trigger${selected?.value === "" ? " placeholder" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => {
          setActiveIndex(selectedIndex);
          setOpen((current) => !current);
        }}
        onKeyDown={onKeyDown}
      >
        <span>{selected?.label}</span>
        <span className="dropdown-chevron" aria-hidden="true" />
      </button>
      {required && (
        <input className="dropdown-required" tabIndex={-1} required value={value} onChange={() => {}} aria-hidden="true" />
      )}
      {menu && createPortal(menu, document.body)}
    </div>
  );
}
