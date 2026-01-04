import { useState } from 'react';
import { Save, Database, Bot, Users, Bell, Globe, Trash2 } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';

export function SettingsPanel() {
  const [settings, setSettings] = useState({
    // General
    language: 'en-my',
    timezone: 'Asia/Kuala_Lumpur',
    itemsPerPage: '20',

    // AI Settings
    aiModel: 'gpt-4',
    searchConfidence: '0.7',
    autoTag: true,
    suggestMetadata: true,

    // Notifications
    emailNotifications: true,
    newUploads: true,
    searchAlerts: false,
    systemUpdates: true,

    // Database
    autoBackup: true,
    backupFrequency: 'daily',
    storageQuota: '1000',
  });

  type User = { name: string; email: string; role: string };
  const [users, setUsers] = useState<User[]>([
    { name: 'Ahmad Ibrahim', role: 'Senior Curator', email: 'ahmad@warisan.gov.my' },
    { name: 'Siti Nurhaliza', role: 'Curator', email: 'siti@warisan.gov.my' },
    { name: 'Lee Wei Ming', role: 'Assistant Curator', email: 'lee@warisan.gov.my' },
  ]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState<User>({ name: '', email: '', role: 'Curator' });

  const handleSave = () => {
    // TODO: Save settings to backend
    toast.success('Settings saved successfully');
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-stone-800 mb-2">Settings</h1>
        <p className="text-stone-500">Manage your archive system preferences and configurations</p>
      </div>

      <Tabs defaultValue="general" className="space-y-6">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="ai">AI & Search</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="database">Database</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
        </TabsList>

        {/* General Settings */}
        <TabsContent value="general">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="w-5 h-5" />
                General Settings
              </CardTitle>
              <CardDescription>Configure basic system preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="language">Language</Label>
                  <Select
                    value={settings.language}
                    onValueChange={(value) => setSettings({ ...settings, language: value })}
                  >
                    <SelectTrigger id="language">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en-my">English (Malaysia)</SelectItem>
                      <SelectItem value="ms-my">Bahasa Melayu</SelectItem>
                      <SelectItem value="zh-cn">中文</SelectItem>
                      <SelectItem value="ta-my">தமிழ்</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="timezone">Timezone</Label>
                  <Select
                    value={settings.timezone}
                    onValueChange={(value) => setSettings({ ...settings, timezone: value })}
                  >
                    <SelectTrigger id="timezone">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Asia/Kuala_Lumpur">Kuala Lumpur (GMT+8)</SelectItem>
                      <SelectItem value="Asia/Singapore">Singapore (GMT+8)</SelectItem>
                      <SelectItem value="Asia/Jakarta">Jakarta (GMT+7)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="itemsPerPage">Items per page</Label>
                <Select
                  value={settings.itemsPerPage}
                  onValueChange={(value) => setSettings({ ...settings, itemsPerPage: value })}
                >
                  <SelectTrigger id="itemsPerPage">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI Settings */}
        <TabsContent value="ai">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="w-5 h-5" />
                AI & Search Configuration
              </CardTitle>
              <CardDescription>Configure AI model and search behavior</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="aiModel">AI Model</Label>
                <Select
                  value={settings.aiModel}
                  onValueChange={(value) => setSettings({ ...settings, aiModel: value })}
                >
                  <SelectTrigger id="aiModel">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gpt-4">GPT-4 (Recommended)</SelectItem>
                    <SelectItem value="gpt-3.5-turbo">GPT-3.5 Turbo (Faster)</SelectItem>
                    <SelectItem value="claude-3">Claude 3</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="searchConfidence">Search Confidence Threshold</Label>
                <Select
                  value={settings.searchConfidence}
                  onValueChange={(value) => setSettings({ ...settings, searchConfidence: value })}
                >
                  <SelectTrigger id="searchConfidence">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0.5">50% - Show more results</SelectItem>
                    <SelectItem value="0.7">70% - Balanced (Recommended)</SelectItem>
                    <SelectItem value="0.9">90% - High precision</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Separator />

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Auto-tagging</Label>
                    <p className="text-sm text-stone-500">Automatically generate tags for uploaded items</p>
                  </div>
                  <Switch
                    checked={settings.autoTag}
                    onCheckedChange={(checked) => setSettings({ ...settings, autoTag: checked })}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>AI Metadata Suggestions</Label>
                    <p className="text-sm text-stone-500">Get AI-powered metadata recommendations</p>
                  </div>
                  <Switch
                    checked={settings.suggestMetadata}
                    onCheckedChange={(checked) => setSettings({ ...settings, suggestMetadata: checked })}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications */}
        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="w-5 h-5" />
                Notification Preferences
              </CardTitle>
              <CardDescription>Manage how you receive notifications</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Email Notifications</Label>
                  <p className="text-sm text-stone-500">Receive notifications via email</p>
                </div>
                <Switch
                  checked={settings.emailNotifications}
                  onCheckedChange={(checked) => setSettings({ ...settings, emailNotifications: checked })}
                />
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>New Uploads</Label>
                  <p className="text-sm text-stone-500">Notify when new items are added</p>
                </div>
                <Switch
                  checked={settings.newUploads}
                  onCheckedChange={(checked) => setSettings({ ...settings, newUploads: checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Search Alerts</Label>
                  <p className="text-sm text-stone-500">Alerts for saved search queries</p>
                </div>
                <Switch
                  checked={settings.searchAlerts}
                  onCheckedChange={(checked) => setSettings({ ...settings, searchAlerts: checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>System Updates</Label>
                  <p className="text-sm text-stone-500">Important system announcements</p>
                </div>
                <Switch
                  checked={settings.systemUpdates}
                  onCheckedChange={(checked) => setSettings({ ...settings, systemUpdates: checked })}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Database */}
        <TabsContent value="database">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="w-5 h-5" />
                Database & Storage
              </CardTitle>
              <CardDescription>Manage backup and storage settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Automatic Backups</Label>
                  <p className="text-sm text-stone-500">Enable scheduled database backups</p>
                </div>
                <Switch
                  checked={settings.autoBackup}
                  onCheckedChange={(checked) => setSettings({ ...settings, autoBackup: checked })}
                />
              </div>

              {settings.autoBackup && (
                <div className="space-y-2">
                  <Label htmlFor="backupFrequency">Backup Frequency</Label>
                  <Select
                    value={settings.backupFrequency}
                    onValueChange={(value) => setSettings({ ...settings, backupFrequency: value })}
                  >
                    <SelectTrigger id="backupFrequency">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hourly">Every Hour</SelectItem>
                      <SelectItem value="daily">Daily</SelectItem>
                      <SelectItem value="weekly">Weekly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <Separator />

              <div className="space-y-2">
                <Label htmlFor="storageQuota">Storage Quota (GB)</Label>
                <Input
                  id="storageQuota"
                  type="number"
                  value={settings.storageQuota}
                  onChange={(e) => setSettings({ ...settings, storageQuota: e.target.value })}
                />
                <p className="text-xs text-stone-500">Current usage: 347 GB / {settings.storageQuota} GB</p>
              </div>

              <div className="flex gap-2">
                <Button variant="outline" className="flex-1">
                  <Database className="w-4 h-4 mr-2" />
                  Backup Now
                </Button>
                <Button variant="outline" className="flex-1">
                  <Database className="w-4 h-4 mr-2" />
                  Restore Backup
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Users */}
        <TabsContent value="users">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="w-5 h-5" />
                User Management
              </CardTitle>
              <CardDescription>Manage curator access and permissions</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Active Users</Label>
                <div className="border border-stone-200 rounded-lg divide-y">
                  {users.map((user, idx) => (
                    <div key={user.email} className="p-4 flex items-center justify-between">
                      <div>
                        <p className="text-stone-800">{user.name}</p>
                        <p className="text-sm text-stone-500">{user.email}</p>
                      </div>
                      <div className="text-right flex items-center gap-3">
                        <p className="text-sm text-stone-600">{user.role}</p>
                        <Button variant="ghost" size="sm" className="text-xs text-red-600" onClick={() => {
                          setUsers(users.filter((_, i) => i !== idx));
                          toast.success('User removed');
                        }}>
                          <Trash2 className="w-4 h-4 mr-1" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <Button className="w-full bg-forest hover:bg-forest" onClick={() => setInviteOpen(true)}>
                <Users className="w-4 h-4 mr-2" />
                Invite New User
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Save Button */}
      <div className="mt-6 flex justify-end">
        <Button onClick={handleSave} className="bg-forest hover:bg-forest">
          <Save className="w-4 h-4 mr-2" />
          Save All Settings
        </Button>
      </div>

      <Dialog open={inviteOpen} onOpenChange={(open) => { if (!open) setInviteOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite New User</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="inv-name">Full Name</Label>
              <Input id="inv-name" value={invite.name} onChange={(e) => setInvite({ ...invite, name: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="inv-email">Email</Label>
              <Input id="inv-email" type="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="inv-role">Role</Label>
              <Select value={invite.role} onValueChange={(value) => setInvite({ ...invite, role: value })}>
                <SelectTrigger id="inv-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Senior Curator">Senior Curator</SelectItem>
                  <SelectItem value="Curator">Curator</SelectItem>
                  <SelectItem value="Assistant Curator">Assistant Curator</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
              <Button onClick={() => {
                if (!invite.name || !invite.email) {
                  toast.error('Name and email are required');
                  return;
                }
                setUsers([{ ...invite }, ...users]);
                toast.success('Invitation sent');
                setInvite({ name: '', email: '', role: 'Curator' });
                setInviteOpen(false);
              }}>Send Invite</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
