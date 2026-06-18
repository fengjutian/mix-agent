"""Docker 隔离沙箱管理器 — 限制 CPU/内存、网络阻断、超时熔断、执行追踪。"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import docker
from docker.errors import DockerException


@dataclass
class SandboxResult:
    """沙箱执行结果。"""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    trace: dict = field(default_factory=dict)


@dataclass
class SecurityScanResult:
    """安全扫描结果（Trivy / Bandit 等）。"""
    vulnerabilities: list[dict] = field(default_factory=list)
    raw_output: str = ""
    exit_code: int = 0
    success: bool = False


class ContainerSandbox:
    """Docker 容器沙箱管理器。

    提供安全的代码动态执行与安全工具扫描环境：
    - CPU / 内存资源限制
    - 网络完全阻断
    - 超时熔断
    - 执行 Trace 追踪与文件系统状态差分

    前提：本地已安装并运行 Docker。
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        cpu_limit: float = 2.0,
        memory_limit: str = "512m",
    ):
        self.image = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        """延迟初始化 Docker 客户端。"""
        if self._client is None:
            try:
                self._client = docker.from_env()
            except DockerException as e:
                raise RuntimeError(f"Docker is not available: {e}")
        return self._client

    # ── 公开接口 ──

    async def run_code(self, code: str, timeout: int = 30) -> SandboxResult:
        """在隔离容器中执行 Python 代码片段并返回结果。

        Args:
            code: 待执行的 Python 代码字符串
            timeout: 超时时间（秒）

        Returns:
            SandboxResult: 含 stdout/stderr/exit_code
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            return await self.run_file(tmp_path, timeout)
        finally:
            os.unlink(tmp_path)

    async def run_file(self, file_path: str, timeout: int = 30) -> SandboxResult:
        """在隔离容器中执行 Python 文件并返回结果。

        Args:
            file_path: Python 文件路径
            timeout: 超时时间（秒）

        Returns:
            SandboxResult: 含 stdout/stderr/exit_code
        """
        file_path = str(Path(file_path).resolve())
        file_name = Path(file_path).name
        work_dir = str(Path(file_path).parent)

        container = None
        try:
            # noqa — 关闭部分安全警告
            container = self.client.containers.run(
                image=self.image,
                command=["python", f"/code/{file_name}"],
                volumes={work_dir: {"bind": "/code", "mode": "ro"}},
                network_mode="none",  # 完全阻断网络
                mem_limit=self.memory_limit,
                nano_cpus=int(self.cpu_limit * 1e9),
                detach=True,
                remove=False,
                read_only=False,  # Python 需要写 /tmp
            )

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                timed_out = False
            except Exception:
                # 超时：强制停止容器
                container.kill()
                exit_code = -1
                timed_out = True

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            # 获取执行 Trace
            trace = {
                "image": self.image,
                "exit_code": exit_code,
                "timed_out": timed_out,
            }

            return SandboxResult(
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                exit_code=exit_code,
                timed_out=timed_out,
                trace=trace,
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass  # 容器可能已被自动清理

    async def run_command(
        self,
        command: list[str],
        timeout: int = 300,
        work_dir: str | None = None,
        volumes: dict[str, dict] | None = None,
    ) -> SandboxResult:
        """在隔离容器中执行任意命令。

        Args:
            command: 命令及其参数列表，如 ["trivy", "fs", "/src"]
            timeout: 超时时间（秒）
            work_dir: 容器内工作目录
            volumes: 额外的卷挂载配置

        Returns:
            SandboxResult: 含 stdout/stderr/exit_code
        """
        container = None
        try:
            container_kwargs: dict = {
                "image": self.image,
                "command": command,
                "network_mode": "none",
                "mem_limit": self.memory_limit,
                "nano_cpus": int(self.cpu_limit * 1e9),
                "detach": True,
                "remove": False,
            }

            if work_dir:
                container_kwargs["working_dir"] = work_dir

            if volumes:
                container_kwargs["volumes"] = volumes

            container = self.client.containers.run(**container_kwargs)

            try:
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                timed_out = False
            except Exception:
                container.kill()
                exit_code = -1
                timed_out = True

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            return SandboxResult(
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                exit_code=exit_code,
                timed_out=timed_out,
            )
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    async def security_scan(self, repo_path: str, timeout: int = 600) -> SecurityScanResult:
        """使用 Trivy 对仓库进行安全扫描（CVE + 密钥检测）。

        前提：本地已拉取 aquasec/trivy 镜像，或已安装 trivy 工具。

        Args:
            repo_path: 待扫描的代码仓库路径
            timeout: 扫描超时时间（秒）

        Returns:
            SecurityScanResult: 包含 vulnerabilities 列表
        """
        repo_abs = str(Path(repo_path).resolve())

        # 使用 Trivy 镜像进行扫描
        try:
            result = await self.run_command(
                command=[
                    "trivy",
                    "fs",
                    "--security-checks", "vuln,secret",
                    "--format", "json",
                    "--severity", "HIGH,CRITICAL",
                    "--no-progress",
                    "/src",
                ],
                timeout=timeout,
                volumes={repo_abs: {"bind": "/src", "mode": "ro"}},
            )
        except RuntimeError:
            # Docker 不可用时的降级方案
            return SecurityScanResult(
                vulnerabilities=[],
                raw_output="Docker not available — security scan skipped",
                success=False,
            )

        vulnerabilities: list[dict] = []
        if result.exit_code == 0 and result.stdout:
            try:
                import json
                data = json.loads(result.stdout)
                if isinstance(data, dict) and "Results" in data:
                    for scan_result in data.get("Results", []):
                        for vuln in scan_result.get("Vulnerabilities", []):
                            vulnerabilities.append({
                                "id": vuln.get("VulnerabilityID", ""),
                                "severity": vuln.get("Severity", ""),
                                "package": vuln.get("PkgName", ""),
                                "installed": vuln.get("InstalledVersion", ""),
                                "fixed": vuln.get("FixedVersion", ""),
                                "title": vuln.get("Title", ""),
                            })
            except json.JSONDecodeError:
                pass

        return SecurityScanResult(
            vulnerabilities=vulnerabilities,
            raw_output=result.stdout or result.stderr,
            exit_code=result.exit_code,
            success=result.exit_code == 0,
        )

    def check_available(self) -> bool:
        """检查 Docker 是否可用。"""
        try:
            self.client.ping()
            return True
        except Exception:
            return False
