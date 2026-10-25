"use client";

import { ChatPanel } from "@/components/chat-panel";
import { LandingPage } from "@/components/landing-page";
import { NoticeBanner, WorkspaceHeader } from "@/components/workspace-chrome";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { WelcomePanel } from "@/components/welcome-panel";
import { ServerDialog } from "@/components/server-dialog";
import { useShellmate } from "@/hooks/use-shellmate";

export default function ShellmateApp() {
  const shellmate = useShellmate();
  const { auth, connectedServer } = shellmate;

  if (!auth) return <LandingPage onAuthenticated={shellmate.signIn} />;

  return (
    <main className={`workspace ${connectedServer ? "workspace-chat" : ""}`}>
      <WorkspaceSidebar
        user={auth}
        servers={shellmate.servers}
        connectedServer={connectedServer}
        sessions={shellmate.sessions}
        activeSession={shellmate.activeSession}
        loadingServers={shellmate.loadingServers}
        busy={shellmate.busy}
        onRegisterServer={() => shellmate.setServerDialog(true)}
        onConnectServer={shellmate.connectServer}
        onSelectSession={shellmate.selectSession}
        onNewChat={shellmate.newChat}
        onLogout={shellmate.logout}
      />

      <section className={`main-panel ${connectedServer ? "main-panel-chat" : ""}`}>
        {!connectedServer && <WorkspaceHeader
          serverTitle="No server connected"
          onRegisterServer={() => shellmate.setServerDialog(true)}
        />}
        {!connectedServer && shellmate.notice && (
          <NoticeBanner
            message={shellmate.notice.message}
            type={shellmate.notice.type}
            onDismiss={shellmate.clearNotice}
          />
        )}
        {connectedServer ? (
          <ChatPanel
            server={connectedServer}
            activeSession={shellmate.activeSession}
            messages={shellmate.messages}
            draft={shellmate.draft}
            busy={shellmate.busy}
            activity={shellmate.activity}
            inlineNotice={shellmate.notice ?? undefined}
            onDismissNotice={shellmate.clearNotice}
            onDeleteChat={shellmate.removeChat}
            onDisconnect={shellmate.disconnectServer}
            onDraftChange={shellmate.setDraft}
            onSubmit={shellmate.sendMessage}
            onUseSuggestion={shellmate.setDraft}
            onRetry={shellmate.retryMessage}
          />
        ) : (
          <WelcomePanel
            email={auth.email}
            onRegisterServer={() => shellmate.setServerDialog(true)}
          />
        )}
      </section>

      {shellmate.serverDialog && (
        <ServerDialog
          token={auth.token}
          onClose={() => shellmate.setServerDialog(false)}
          onCreated={shellmate.handleServerCreated}
        />
      )}
    </main>
  );
}
