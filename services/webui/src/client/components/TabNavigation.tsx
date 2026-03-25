import type { Tab } from '../types';

interface TabNavigationProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

export default function TabNavigation({ tabs, activeTab, onChange }: TabNavigationProps) {
  return (
    <div className="tab-nav">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`tab-item ${activeTab === tab.id ? 'tab-item-active' : ''}`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
