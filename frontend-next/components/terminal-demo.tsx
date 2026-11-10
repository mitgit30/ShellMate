"use client";

export function TerminalDemo() {
  return (
    <section className="terminal-demo" aria-labelledby="terminal-demo-title">
      <div className="terminal-demo-header">
        <div className="terminal-window-dots" aria-hidden="true"><i /><i /><i /></div>
        <span id="terminal-demo-title">Server investigation</span>
        <span className="demo-status">Example</span>
      </div>

      <div className="demo-prompt">
        <span className="demo-speaker">You</span>
        <p>why is disk usage high?</p>
      </div>

      <div className="demo-step demo-step-disk">
        <div className="demo-command">
          <code>df -h</code>
          <span className="risk-badge risk-readonly">Read-only</span>
        </div>
        <pre>{"Filesystem  Size  Used  Avail  Use%  Mounted on\n/dev/root    30G   24G   5.1G   83%   /"}</pre>
      </div>

      <div className="demo-step">
        <div className="demo-command">
          <code>du -sh /var/*</code>
          <span className="risk-badge risk-readonly">Read-only</span>
        </div>
        <pre className="demo-output-full">{"18G  /var/lib\n2.1G /var/log\n1.4G /var/cache"}</pre>
        <pre className="demo-output-compact">18G /var/lib · 2.1G /var/log</pre>
      </div>

      <div className="demo-summary">
        <span className="demo-summary-mark" aria-hidden="true">&gt;_</span>
        <p><strong>ShellMate</strong> Most space is in <code>/var/lib</code>; logs are also contributing.</p>
      </div>
    </section>
  );
}
