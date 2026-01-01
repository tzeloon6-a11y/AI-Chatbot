import logo from '../assets/logo.png';
import { MessageSquare, Archive, Settings } from 'lucide-react';
import type { ViewMode } from '../App';

type SidebarProps = {
  currentView: ViewMode;
  onViewChange: (view: ViewMode) => void;
};

type NavItem = {
  id: ViewMode;
  icon: typeof MessageSquare;
  label: string;
  subtitle?: string;
};

export function Sidebar({ currentView, onViewChange }: SidebarProps) {
  const navItems: NavItem[] = [
    { id: 'chat', icon: MessageSquare, label: 'AI Search', subtitle: 'Search archives' },
    { id: 'dashboard', icon: Archive, label: 'Dashboard', subtitle: 'Curator tools' },
    { id: 'settings', icon: Settings, label: 'Settings', subtitle: 'Configuration' },
  ];

  return (
    <aside className="w-64 bg-gradient-to-b from-amber-50 to-stone-100 border-r border-stone-200 flex flex-col">
      {/* Logo/Brand */}
      <div className="p-6 border-b border-stone-200">
        <div className="flex items-center gap-3">
          <img
            src={logo}
            alt="Logo"
            className="w-10 h-10 object-cover"
          />
          <div>
            <h1 className="text-stone-800 font-semibold">Badan Warisan Malaysia</h1>
            <p className="text-xs text-stone-600">Digital Archive</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;

            return (
              <li key={item.id}>
                <button
                  onClick={() => onViewChange(item.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${isActive
                    ? 'bg-forest text-white shadow-md'
                    : 'text-stone-700 hover:bg-stone-200'
                    }`}
                >
                  <Icon className="w-5 h-5 shrink-0" />
                  <div className="text-left flex-1">
                    <div className="text-sm">{item.label}</div>
                    {item.subtitle && (
                      <div className={`text-xs ${isActive ? 'text-white/80' : 'text-stone-500'}`}>
                        {item.subtitle}
                      </div>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-stone-200">
        <div className="text-xs text-stone-500 text-center">
          Badan Warisan Negara
          <br />
          © 2025
        </div>
      </div>
    </aside>
  );
}
