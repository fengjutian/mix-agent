import { useLocation, useNavigate } from "react-router-dom";

interface ActivityItem {
  id: string;
  label: string;
  route: string;
  icon: React.ReactNode;
}

const activities: ActivityItem[] = [
  {
    id: "home",
    label: "Tasks",
    route: "/",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    id: "approvals",
    label: "Approvals",
    route: "/approvals",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
  },
  {
    id: "cost",
    label: "Cost",
    route: "/settings",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
  },
];

export default function ActivityBar() {
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (item: ActivityItem) => {
    if (item.route === "/") return location.pathname === "/";
    return location.pathname.startsWith(item.route);
  };

  return (
    <nav className="activity-bar" aria-label="Main navigation">
      <div className="activity-bar__top">
        {activities.map((item) => (
          <button
            key={item.id}
            className={`activity-bar__item${isActive(item) ? " activity-bar__item--active" : ""}`}
            onClick={() => navigate(item.route)}
            title={item.label}
            aria-label={item.label}
          >
            <div className="activity-bar__indicator" />
            {item.icon}
          </button>
        ))}
      </div>
    </nav>
  );
}
