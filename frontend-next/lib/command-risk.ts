import type { CommandRisk } from "@/types/domain";

const DESTRUCTIVE_COMMAND = /\b(?:rm|rmdir|reboot|shutdown|poweroff|mkfs(?:\.[a-z0-9]+)?|wipefs|shred|truncate|killall)\b|\bdd\s+if=|\bsystemctl\s+(?:stop|restart|disable|mask)\b|\b(?:apt|apt-get|dnf|yum|pip|npm)\s+(?:remove|purge|uninstall)\b|\bdocker\s+(?:rm|system\s+prune|compose\s+down)\b/i;
const CONTROLLED_COMMAND = /\b(?:mkdir|touch|cp|mv|chmod|chown|tee|install|apt|apt-get|dnf|yum|pip|npm|systemctl|docker|ufw|iptables)\b|(?:^|\s)(?:>|>>)(?:\s|$)/i;
const READ_ONLY_COMMAND = /^(?:sudo\s+)*(?:cat|df|du|free|uptime|uname|whoami|hostname|pwd|ls|find|ps|top|systemctl\s+status|journalctl|ip\s+(?:addr|address|route|link)|ss|netstat|grep|which|command\s+-v|id|date|wc|head|tail|stat|mount|lscpu|lsblk|vmstat|who|last|printenv|env|sed|awk)\b/i;

/** Informational UI estimate only; this does not authorize or block execution. */
export function estimateCommandRisk(command: string): CommandRisk {
  if (DESTRUCTIVE_COMMAND.test(command)) return "destructive";
  if (CONTROLLED_COMMAND.test(command)) return "controlled";

  const segments = command
    .split(/&&|\|\||[;|]/)
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (segments.length > 0 && segments.every((segment) => READ_ONLY_COMMAND.test(segment))) {
    return "read-only";
  }

  return "controlled";
}
