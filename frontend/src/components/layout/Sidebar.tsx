import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink } from "react-router-dom";
import {
  ChartNoAxesCombined,
  GitCompareArrows,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  SearchCheck,
  TriangleAlert,
  UserCircle,
  type LucideIcon,
} from "lucide-react";
import { useLogout, useMe } from "../../api/queries";
import { Drawer } from "../ui/Drawer";

interface NavLeaf {
  label: string;
  to: string;
  icon: LucideIcon;
  comingSoon?: boolean;
}

interface NavGroup {
  label: string;
  items: NavLeaf[];
}

/** The application shell's nav tree, grouped exactly as the product
 * information architecture: one destination per real page. There is no separate
 * "Transactions" destination -- transaction-level detail already lives
 * on Reconciliation and the Financial Impact drill-down, so a nav item
 * pointing at a Coming Soon page here would only dead-end next to a
 * working equivalent. */
const NAV_TREE: NavGroup[] = [
  { label: "Overview", items: [{ label: "Overview", to: "/overview", icon: LayoutDashboard }] },
  {
    label: "Operations",
    items: [
      { label: "Reconciliation", to: "/reconciliation", icon: GitCompareArrows },
      { label: "Exceptions", to: "/exceptions", icon: TriangleAlert },
    ],
  },
  {
    label: "Investigations",
    items: [{ label: "Investigations", to: "/investigations", icon: SearchCheck }],
  },
  {
    label: "Insights",
    items: [{ label: "Reports", to: "/reports", icon: ChartNoAxesCombined }],
  },
];

/** Settings has no page yet -- stays an inert placeholder. The
 * authenticated profile slot below it is real (see UserFooterItem). */
const NAV_FOOTER: { label: string; icon: LucideIcon }[] = [
  { label: "Settings", icon: Settings },
];

const COLLAPSE_STORAGE_KEY = "ledgerlens.sidebar.collapsed";

function readStoredCollapsed(): boolean {
  try {
    return sessionStorage.getItem(COLLAPSE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function ComingSoonTag() {
  return (
    <span className="rounded-[3px] border border-navy-ink/40 px-1 py-0.5 font-mono text-[9px] font-medium uppercase tracking-wider text-navy-ink/70">
      Soon
    </span>
  );
}

/** The sidebar's own `overflow-y-auto` (needed so a tall nav tree can
 * scroll) forces its `overflow-x` to compute to `auto` too, per the CSS
 * overflow spec -- so a tooltip positioned with `absolute` never becomes
 * visible once it pokes out past the sidebar's own width, it's silently
 * clipped. Portaling it to `document.body` and positioning it with the
 * anchor's real viewport coordinates sidesteps that clipping entirely.
 * The anchor ref stays owned by the caller (not bundled into this
 * hook's return value) so it's read only from the show/hide handlers,
 * never at render time. */
function useTooltipState(enabled: boolean) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  function showAt(rect: DOMRect | undefined) {
    if (!enabled || !rect) return;
    setPos({ top: rect.top + rect.height / 2, left: rect.right + 8 });
    setOpen(true);
  }
  function hide() {
    setOpen(false);
  }

  return { open: enabled && open, pos, showAt, hide };
}

function TooltipBubble({ text, top, left }: { text: string; top: number; left: number }) {
  return createPortal(
    <span
      role="tooltip"
      style={{ position: "fixed", top, left, transform: "translateY(-50%)" }}
      className="pointer-events-none z-50 whitespace-nowrap rounded-md bg-ink px-2 py-1 font-mono text-[11px] text-white shadow-lg"
    >
      {text}
    </span>,
    document.body,
  );
}

/** One nav row. When collapsed, the label is dropped from the flow and
 * replaced by a hover/focus tooltip so icon-only navigation never stays
 * ambiguous -- an `aria-label` on the link itself covers screen readers
 * regardless of hover state. */
function NavItem({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavLeaf;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const tooltip = item.comingSoon ? `${item.label} (coming soon)` : item.label;
  const anchorRef = useRef<HTMLAnchorElement>(null);
  const tip = useTooltipState(collapsed);
  const showTip = () => tip.showAt(anchorRef.current?.getBoundingClientRect());

  return (
    <>
      <NavLink
        ref={anchorRef}
        to={item.to}
        onClick={onNavigate}
        onMouseEnter={showTip}
        onMouseLeave={tip.hide}
        onFocus={showTip}
        onBlur={tip.hide}
        aria-label={item.label}
        className={({ isActive }) =>
          `relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
            collapsed ? "justify-center px-0" : ""
          } ${isActive ? "bg-white/10 text-white" : "text-navy-ink hover:bg-white/5 hover:text-white"}`
        }
      >
        <Icon size={18} strokeWidth={2} className="shrink-0" aria-hidden="true" />
        {!collapsed && (
          <>
            <span className="truncate">{item.label}</span>
            {item.comingSoon && <ComingSoonTag />}
          </>
        )}
      </NavLink>
      {tip.open && <TooltipBubble text={tooltip} top={tip.pos.top} left={tip.pos.left} />}
    </>
  );
}

function NavTree({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex flex-col gap-4">
      {NAV_TREE.map((group) => (
        <div key={group.label}>
          {!collapsed && (
            <div className="px-3 pb-1 font-mono text-[10px] font-medium uppercase tracking-wider text-navy-ink/60">
              {group.label}
            </div>
          )}
          <div className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <NavItem key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function NavFooterItem({
  label,
  icon: Icon,
  collapsed,
}: {
  label: string;
  icon: LucideIcon;
  collapsed: boolean;
}) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const tip = useTooltipState(collapsed);
  const showTip = () => tip.showAt(anchorRef.current?.getBoundingClientRect());

  return (
    <>
      <span
        ref={anchorRef}
        tabIndex={0}
        onMouseEnter={showTip}
        onMouseLeave={tip.hide}
        onFocus={showTip}
        onBlur={tip.hide}
        className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-navy-ink/50 ${
          collapsed ? "justify-center px-0" : ""
        }`}
      >
        <Icon size={18} strokeWidth={2} className="shrink-0" aria-hidden="true" />
        {!collapsed && (
          <>
            <span className="truncate">{label}</span>
            <ComingSoonTag />
          </>
        )}
      </span>
      {tip.open && <TooltipBubble text={`${label} (coming soon)`} top={tip.pos.top} left={tip.pos.left} />}
    </>
  );
}

/** The authenticated user's identity + role, and a Sign out action --
 * the real thing the old inert "User Profile" placeholder was left
 * for. Same slot, same collapsed/tooltip behavior as every other
 * footer item, so this never reads as a layout change. */
function UserFooterItem({ collapsed }: { collapsed: boolean }) {
  const me = useMe();
  const logout = useLogout();
  const anchorRef = useRef<HTMLDivElement>(null);
  const tip = useTooltipState(collapsed);
  const showTip = () => tip.showAt(anchorRef.current?.getBoundingClientRect());

  if (!me.data) return null;

  const roleLabel = me.data.role === "reviewer" ? "Reviewer" : "Analyst";
  const tooltip = `${me.data.email} · ${roleLabel}`;

  return (
    <>
      <div
        ref={anchorRef}
        tabIndex={0}
        role={collapsed ? "button" : undefined}
        aria-label={collapsed ? "Sign out" : undefined}
        onClick={collapsed ? () => logout.mutate() : undefined}
        onKeyDown={
          collapsed
            ? (event) => {
                if (event.key === "Enter" || event.key === " ") logout.mutate();
              }
            : undefined
        }
        onMouseEnter={showTip}
        onMouseLeave={tip.hide}
        onFocus={showTip}
        onBlur={tip.hide}
        className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-navy-ink ${
          collapsed ? "cursor-pointer justify-center px-0 hover:bg-white/10 hover:text-white" : ""
        }`}
      >
        <UserCircle size={18} strokeWidth={2} className="shrink-0" aria-hidden="true" />
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs text-white">{me.data.email}</div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-navy-ink/70">
                {roleLabel}
              </div>
            </div>
            <button
              type="button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              aria-label="Sign out"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-navy-ink hover:bg-white/10 hover:text-white disabled:opacity-50"
            >
              <LogOut size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </>
        )}
      </div>
      {tip.open && (
        <TooltipBubble
          text={collapsed ? tooltip : "Sign out"}
          top={tip.pos.top}
          left={tip.pos.left}
        />
      )}
    </>
  );
}

function NavFooter({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="mt-auto flex flex-col gap-0.5 border-t border-navy-border pt-3">
      {NAV_FOOTER.map(({ label, icon }) => (
        <NavFooterItem key={label} label={label} icon={icon} collapsed={collapsed} />
      ))}
      <UserFooterItem collapsed={collapsed} />
    </div>
  );
}

/** Persistent left sidebar -- deep navy, the one large anchor surface in
 * the app; the workspace stays white/light per the palette. Collapse
 * state is remembered for the session (not permanently, since there's no
 * user profile yet to own that preference). */
export function Sidebar() {
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);

  useEffect(() => {
    try {
      sessionStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // sessionStorage unavailable (private mode, etc.) -- collapse
      // state simply won't persist across reloads this session.
    }
  }, [collapsed]);

  return (
    <aside
      className={`sticky top-0 hidden h-screen shrink-0 flex-col gap-6 overflow-y-auto bg-navy px-3 py-5 transition-[width] duration-200 ease-out sm:flex ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <div className={`flex items-center ${collapsed ? "flex-col gap-3" : "justify-between px-2"}`}>
        {collapsed ? (
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 font-mono text-xs font-semibold text-white">
            L
          </span>
        ) : (
          <span className="font-mono text-sm font-medium tracking-tight text-white">
            Ledger<span className="text-accent">Lens</span>
          </span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-navy-ink hover:bg-white/10 hover:text-white"
        >
          {collapsed ? (
            <PanelLeftOpen size={16} strokeWidth={2} aria-hidden="true" />
          ) : (
            <PanelLeftClose size={16} strokeWidth={2} aria-hidden="true" />
          )}
        </button>
      </div>
      <NavTree collapsed={collapsed} />
      <NavFooter collapsed={collapsed} />
    </aside>
  );
}

/** Below `sm`, the sidebar becomes a full off-canvas drawer -- reusing
 * the existing Drawer gets outside-click-close and Escape-close for
 * free, and each link closes it on navigate. Never shown icon-only on
 * mobile: there's no persistent chrome to collapse against. */
export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 font-mono text-[13px] font-medium text-ink sm:hidden"
      >
        <Menu size={16} strokeWidth={2} aria-hidden="true" />
        Menu
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title="Navigate">
        {/* Reclaim the Drawer's light padding area so the navy-themed
            nav items render on their intended dark background. */}
        <div className="-m-5 flex min-h-full flex-col gap-6 bg-navy p-5">
          <span className="px-2 font-mono text-sm font-medium tracking-tight text-white">
            Ledger<span className="text-accent">Lens</span>
          </span>
          <NavTree collapsed={false} onNavigate={() => setOpen(false)} />
          <NavFooter collapsed={false} />
        </div>
      </Drawer>
    </>
  );
}
