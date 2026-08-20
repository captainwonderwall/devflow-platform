class Devflow < Formula
  desc "AI-powered developer workflow scripts"
  homepage "https://github.com/captainwonderwall/devflow"
  url "https://github.com/captainwonderwall/devflow.git",
      tag:      "devflow/v0.1.1",
      revision: "22ddd28bcfbb339db92c61b98284b57dc7d87de1"
  license "MIT"
  head "https://github.com/captainwonderwall/devflow.git", branch: "main"

  depends_on "python@3"

  def install
    libexec.install Dir["*"]

    python_packages = libexec/"python-packages"
    python_packages.mkpath
    Dir["#{libexec}/vendor/*.whl"].each do |whl|
      system "pip3", "install", "--no-deps", "--target=#{python_packages}", whl
    end

    (lib/"devflow/plugins").mkpath
    rm_rf(libexec/"draft-pr/plugins")
    (libexec/"draft-pr/plugins").make_symlink(lib/"devflow/plugins")

    %w[draft-pr address-pr squash-commits finish-issue start-issue].each do |tool|
      (bin/tool).write <<~BASH
        #!/bin/bash
        export PYTHONPATH="#{python_packages}${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 "#{libexec}/#{tool}/#{tool}.py" "$@"
      BASH
      (bin/tool).chmod 0755
    end
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
