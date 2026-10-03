import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import java.io.*; import java.nio.file.*;
public class SeedDump extends GhidraScript {
  public void run() throws Exception {
    String[] a = getScriptArgs();
    java.util.List<String> lines = Files.readAllLines(Paths.get(a[0]));
    for (String l : lines) { l=l.trim(); if (l.isEmpty()) continue;
      Address ad = toAddr(Long.decode(l));
      new DisassembleCommand(ad,null,true).applyTo(currentProgram, monitor);
    }
    for (String l : lines) { l=l.trim(); if (l.isEmpty()) continue;
      Address ad = toAddr(Long.decode(l));
      if (getFunctionAt(ad)==null) new CreateFunctionCmd(ad).applyTo(currentProgram, monitor);
    }
    analyzeChanges(currentProgram);
    PrintWriter pw = new PrintWriter(new FileWriter(a[1]));
    DecompInterface di = new DecompInterface(); di.openProgram(currentProgram);
    for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
      DecompileResults r = di.decompileFunction(f, 60, monitor);
      pw.println("//==== " + f.getName() + " @ " + f.getEntryPoint());
      if (r != null && r.decompileCompleted()) pw.println(r.getDecompiledFunction().getC()); else pw.println("// fail");
    }
    pw.close();
  }
}
