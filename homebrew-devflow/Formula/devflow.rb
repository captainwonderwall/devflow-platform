class Devflow < Formula
  desc "AI-powered developer workflow scripts"
  homepage "https://github.com/captainwonderwall/devflow-platform"
  url "https://github.com/captainwonderwall/devflow-platform.git",
      tag:      "devflow/v1.4.2",
      revision: "7a7051aedb239c603d9dc339ddfb5f6ec95b5d1d"
  license "MIT"
  head "https://github.com/captainwonderwall/devflow-platform.git", branch: "main"

  depends_on "python@3"

  # TODO: update url and sha256 after releasing devflow-sdk/v1.1.0
  resource "devflow-sdk" do
    url "https://github.com/captainwonderwall/devflow-platform/releases/download/devflow-sdk%2Fv1.2.8/devflow_sdk-1.2.8-py3-none-any.whl"
    sha256 "c96c3dd9e008fcf7b3215b1cd9ceaa4f1be909d68332edb2b021db06431b246f"
  end

  resource "questionary" do
    url "https://files.pythonhosted.org/packages/3c/26/1062c7ec1b053db9e499b4d2d5bc231743201b74051c973dadeac80a8f43/questionary-2.1.1-py3-none-any.whl"
    sha256 "a51af13f345f1cdea62347589fbb6df3b290306ab8930713bfae4d475a7d4a59"
  end

  resource "prompt_toolkit" do
    url "https://files.pythonhosted.org/packages/54/6f/84908cad2d6aa5144abcf7b42709fe4fdb459bc640ec7ac5786e7693dabc/prompt_toolkit-3.0.53-py3-none-any.whl"
    sha256 "01c0891d7f9237d5e339f7d3e42cdae80b7534abb1c7c0e3352efba6231492f2"
  end

  resource "wcwidth" do
    url "https://files.pythonhosted.org/packages/96/42/3e5985a0a7e57de470b320c6d6a1a67c844f6737a587f3d44dd13d1819e7/wcwidth-0.8.2-py3-none-any.whl"
    sha256 "d63947694a0539a1d51e01eda7caf800c291020e6cdd7e28ad7b14dd33ad4f85"
  end

  def install
    libexec.install Dir["devflow/*"]

    python_packages = libexec/"python-packages"
    python_packages.mkpath
    resources.each do |r|
      r.stage do
        whl = Dir["*.whl"].first
        system "pip3", "install", "--no-deps", "--target=#{python_packages}", whl || Pathname.pwd
      end
    end

    %w[draft-pr address-pr squash-commits finish-issue start-issue].each do |tool|
      (bin/tool).write <<~BASH
        #!/bin/bash
        export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 "#{libexec}/#{tool}/#{tool}.py" "$@"
      BASH
      (bin/tool).chmod 0755
    end

    (bin/"devflow-plugin").write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/plugin-manager/plugin_loader.py" "$@"
    BASH
    (bin/"devflow-plugin").chmod 0755

    (bin/"devflow-config").write <<~BASH
      #!/bin/bash
      export PYTHONPATH="#{libexec}/plugin-manager:#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
      exec python3 "#{libexec}/devflow-config/devflow-config.py" "$@"
    BASH
    (bin/"devflow-config").chmod 0755
  end

  def caveats
    <<~EOS
      To finish setup, run the shell integration script once:
        bash #{opt_libexec}/scripts/setup-shell.sh
      Then reload your shell:
        source ~/.zshrc
    EOS
  end

  test do
    system "python3", "-c",
      "import sys; sys.path.insert(0, '#{libexec}/python-packages'); import questionary"
  end
end
