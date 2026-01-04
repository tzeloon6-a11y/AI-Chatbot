import { Bell, User } from 'lucide-react';
import { Avatar, AvatarFallback } from './ui/avatar';
import { Button } from './ui/button';

export function TopBar() {
  return (
    <header className="h-16 bg-white border-b border-stone-200 flex items-center justify-between px-6 shadow-sm">
      <div>
        <h1 className="text-stone-800">Badan Warisan Digital Archive</h1>
        <p className="text-xs text-stone-500">Interactive Heritage Collection Management</p>
      </div>

      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="w-5 h-5 text-stone-600" />
          <span className="absolute top-2 right-2 w-2 h-2 bg-forest rounded-full"></span>
        </Button>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-sm text-stone-800">Curator Admin</p>
            <p className="text-xs text-stone-500">Museum Manager</p>
          </div>
          <Avatar>
            <AvatarFallback className="bg-forest text-white">
              <User className="w-5 h-5" />
            </AvatarFallback>
          </Avatar>
        </div>
      </div>
    </header>
  );
}
