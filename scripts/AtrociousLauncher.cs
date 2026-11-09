using System;
using System.Diagnostics;
using System.IO;

namespace Atrocious
{
    class Program
    {
        static void Main(string[] args)
        {
            string baseDir = @"D:\App Development\Software Testing Agent Harness";
            string pythonw = Path.Combine(baseDir, @".venv\Scripts\pythonw.exe");
            string script = Path.Combine(baseDir, @"sentinel\studio\desktop_app.py");

            if (!File.Exists(pythonw))
            {
                pythonw = "pythonw.exe";
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonw;
            psi.Arguments = "\"" + script + "\"";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                string logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Atrocious", "logs");
                Directory.CreateDirectory(logDir);
                File.AppendAllText(Path.Combine(logDir, "launcher_crash.log"), DateTime.Now.ToString() + ": " + ex.ToString() + Environment.NewLine);
            }
        }
    }
}
