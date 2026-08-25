class Devflow < Formula
  desc "AI-powered developer workflow scripts"
  homepage "https://github.com/captainwonderwall/devflow-platform"
  url "https://github.com/captainwonderwall/devflow-platform.git",
      tag:      "devflow/v0.4.1",
      revision: "626a7875d0360ee400202a6c206651e8d8d94dc7"
  license "MIT"
  head "https://github.com/captainwonderwall/devflow-platform.git", branch: "main"

  depends_on "python@3"

  def install
    libexec.install Dir["devflow/*"]

    python_packages = libexec/"python-packages"
    python_packages.mkpath
    Dir["#{libexec}/vendor/*.whl"].each do |whl|
      system "pip3", "install", "--no-deps", "--target=#{python_packages}", whl
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
