# Homebrew formula for wizpatch.
#
# Quick install straight from git (no release needed):
#   brew install --HEAD Deimos-Wizard101/wizpatch/wizpatch
# or, against a local checkout of this formula:
#   brew install --HEAD ./Formula/wizpatch.rb
#
# Stable install works once a `v0.1.0` tag is pushed and the `sha256` below is
# filled in (Homebrew prints the expected value on first fetch, or run:
#   curl -fsSL https://github.com/Deimos-Wizard101/wizpatch/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
class Wizpatch < Formula
  desc "Fast parallel patcher and downloader for Wizard101 game files"
  homepage "https://github.com/Deimos-Wizard101/wizpatch"
  url "https://github.com/Deimos-Wizard101/wizpatch/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "GPL-3.0-or-later"
  head "https://github.com/Deimos-Wizard101/wizpatch.git", branch: "main"

  depends_on "rust" => :build

  def install
    # The `wizpatch` binary target is gated behind the `cli` feature.
    system "cargo", "install", *std_cargo_args, "--features", "cli"
  end

  test do
    assert_match "Usage: wizpatch", shell_output("#{bin}/wizpatch --help 2>&1")
  end
end
