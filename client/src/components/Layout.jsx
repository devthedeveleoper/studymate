import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import { Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';

import { ModeToggle } from './mode-toggle';

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(false)} />

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile Header */}
        <header className="md:hidden flex h-16 shrink-0 items-center justify-between border-b bg-background px-4">
          <div className="flex items-center">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              className="mr-2"
            >
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open sidebar</span>
            </Button>
            <div className="font-heading font-bold text-xl tracking-tight text-primary">StudyMate</div>
          </div>
          <ModeToggle />
        </header>

        {/* Main Content Area */}
        <div className="flex-1 overflow-auto bg-muted/20">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
