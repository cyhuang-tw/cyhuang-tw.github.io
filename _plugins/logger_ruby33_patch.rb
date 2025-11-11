# Ensures Logger initializes @level_override before Jekyll (via github-pages) touches it on Ruby 3.3+
require 'logger'

unless ''.respond_to?(:tainted?)
  class Object
    def tainted?
      false
    end

    def taint
      self
    end

    def untaint
      self
    end
  end
end

module LoggerRuby33Patch
  def level
    @level_override ||= {}
    super
  end
end

Logger.prepend(LoggerRuby33Patch) unless Logger < LoggerRuby33Patch
