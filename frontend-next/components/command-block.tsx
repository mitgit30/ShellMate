import type { ChatCommandBlock, CommandRisk } from "@/types/domain";

const riskLabels: Record<CommandRisk, string> = {
  "read-only": "Read-only",
  controlled: "Controlled",
  destructive: "Destructive",
};

type RiskBadgeProps = {
  risk: CommandRisk;
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  const riskClass = risk === "read-only" ? "read-only" : risk;
  return (
    <span className={"risk-badge risk-" + riskClass} title="Informational estimate only; this does not block command execution." aria-label={"Estimated risk: " + riskLabels[risk]}>
      {riskLabels[risk]}
    </span>
  );
}

type CommandBlockProps = {
  block: ChatCommandBlock;
};

export function CommandBlock({ block }: CommandBlockProps) {
  const output = block.output.trim() || (block.status === "running" ? "Command is running…" : "No output returned.");

  return (
    <section className={"command-block command-" + block.status} aria-label={riskLabels[block.risk] + " command"}>
      <div className="command-block-heading">
        <code><span aria-hidden="true">$</span> {block.command}</code>
        <RiskBadge risk={block.risk} />
      </div>
      <details className="command-output">
        <summary>
          <span className="output-show">Show output</span>
          <span className="output-hide">Hide output</span>
          {block.status !== "running" && <span className="command-result">{
            block.status === "failed" ? "Exit " + (block.exitStatus ?? "error")
              : block.status === "interrupted" ? "Interrupted"
                : "Completed"
          }</span>}
        </summary>
        <pre>{output}</pre>
      </details>
    </section>
  );
}
