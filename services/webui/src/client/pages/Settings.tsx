import { useState } from 'react';
import Card from '../components/Card';
import TabNavigation from '../components/TabNavigation';

export default function Settings() {
  const [activeTab, setActiveTab] = useState('general');

  const tabs = [
    { id: 'general', label: 'General' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'security', label: 'Security' },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gold-400">Settings</h1>
        <p className="text-dark-400 mt-1">Manage application settings</p>
      </div>

      {/* Tab Navigation */}
      <TabNavigation tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab Content */}
      <div className="mt-6">
        {activeTab === 'general' && (
          <Card title="General Settings">
            <div className="space-y-6">
              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">Dark Mode</span>
                    <span className="text-sm text-dark-400">Use dark theme (default)</span>
                  </div>
                  <input type="checkbox" defaultChecked className="w-5 h-5" />
                </label>
              </div>

              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">Compact View</span>
                    <span className="text-sm text-dark-400">Reduce spacing in tables</span>
                  </div>
                  <input type="checkbox" className="w-5 h-5" />
                </label>
              </div>

              <div>
                <label className="block">
                  <span className="text-gold-400 block mb-2">Timezone</span>
                  <select className="input">
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">Eastern Time</option>
                    <option value="America/Chicago">Central Time</option>
                    <option value="America/Denver">Mountain Time</option>
                    <option value="America/Los_Angeles">Pacific Time</option>
                  </select>
                </label>
              </div>
            </div>
          </Card>
        )}

        {activeTab === 'notifications' && (
          <Card title="Notification Settings">
            <div className="space-y-6">
              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">Email Notifications</span>
                    <span className="text-sm text-dark-400">Receive email for important events</span>
                  </div>
                  <input type="checkbox" defaultChecked className="w-5 h-5" />
                </label>
              </div>

              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">System Alerts</span>
                    <span className="text-sm text-dark-400">Get notified about system issues</span>
                  </div>
                  <input type="checkbox" defaultChecked className="w-5 h-5" />
                </label>
              </div>

              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">Weekly Reports</span>
                    <span className="text-sm text-dark-400">Receive weekly summary email</span>
                  </div>
                  <input type="checkbox" className="w-5 h-5" />
                </label>
              </div>
            </div>
          </Card>
        )}

        {activeTab === 'security' && (
          <Card title="Security Settings">
            <div className="space-y-6">
              <div>
                <label className="flex items-center justify-between">
                  <div>
                    <span className="text-gold-400 block">Two-Factor Authentication</span>
                    <span className="text-sm text-dark-400">Add extra security to your account</span>
                  </div>
                  <input type="checkbox" className="w-5 h-5" />
                </label>
              </div>

              <div>
                <label className="block">
                  <span className="text-gold-400 block mb-2">Session Timeout</span>
                  <select className="input">
                    <option value="15">15 minutes</option>
                    <option value="30">30 minutes</option>
                    <option value="60" selected>1 hour</option>
                    <option value="480">8 hours</option>
                  </select>
                </label>
              </div>

              <div className="pt-4 border-t border-dark-700">
                <h3 className="text-gold-400 mb-3">Active Sessions</h3>
                <div className="text-dark-400 text-sm">
                  <p>Current session: This device</p>
                  <p className="text-dark-500 mt-1">Last active: Just now</p>
                </div>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
