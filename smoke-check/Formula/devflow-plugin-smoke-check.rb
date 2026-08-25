class DevflowPluginSmokeCheck < Formula
  desc "devflow plugin: Smoke Check"
  homepage "<your-plugin-homepage>"
  url "https://github.com/<your-org>/smoke-check/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "<sha256-of-tarball>"
  version "0.1.0"

  depends_on "captainwonderwall/devflow/devflow"

  def install
    lib.install "smoke_check.py"
    vendor = lib/"vendor"
    vendor.mkpath
    Dir["vendor/*.whl"].each { |whl| vendor.install whl }
  end

  def post_install
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin",
           "register", "smoke-check",
           "#{opt_lib}/smoke_check.py",
           "--formula", "<your-tap>/smoke-check"
  end

  test do
    system "#{HOMEBREW_PREFIX}/bin/devflow-plugin", "list"
  end
end
