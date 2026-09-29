// Decompile the functions containing each address given as script args; append C to the output file (first arg).
// @category xml1port
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import java.io.*;
import java.util.*;

public class DecompAt extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0], true));
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        Set<Function> done = new HashSet<>();
        for (int i = 1; i < args.length; i++) {
            Address a = toAddr(Long.parseLong(args[i], 16));
            Function f = getFunctionContaining(a);
            if (f == null) {
                disassemble(a);
                f = createFunction(a, null);
            }
            if (f == null) {
                out.println("// no function at " + args[i]);
                continue;
            }
            if (!done.add(f)) continue;
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            out.println("// ===== " + args[i] + " in " + f.getName() + " @ " + f.getEntryPoint());
            if (r.decompileCompleted())
                out.println(r.getDecompiledFunction().getC());
            else
                out.println("// decompile failed: " + r.getErrorMessage());
        }
        out.close();
    }
}
