// Copyright Epic Games, Inc. All Rights Reserved.

#include "DeadlineJobPreset.h"

#include "DeadlineServiceEditorSettings.h"

#include "Widgets/Layout/SBorder.h"
#include "Widgets/SBoxPanel.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(DeadlineJobPreset)

DEFINE_LOG_CATEGORY(LogDeadlineDataAsset);
DEFINE_LOG_CATEGORY(LogDeadlineStruct);

UDeadlineJobPreset::UDeadlineJobPreset()
{
	SetupPluginInfo();
}

/**
 * Retrieves the path of the executable file, adding the desired variant to the end.
 * DesiredExecutableVariant is defined in DeadlineServiceEditorSettings.
 * @return A string representing the path of the executable file.
 */
FString GetExecutablePathWithDesiredVariant()
{
	FString ExecutablePath = FPlatformProcess::ExecutablePath();
	FString ExtensionWithDot = FPaths::GetExtension(ExecutablePath, true);
	ExecutablePath.RemoveFromEnd(ExtensionWithDot);
	FString DesiredExecutableVariant = GetDefault<UDeadlineServiceEditorSettings>()->DesiredExecutableVariant;
	ExecutablePath.RemoveFromEnd(DesiredExecutableVariant);

	TStringBuilder<1024> StringBuilder;
	StringBuilder.Append(ExecutablePath);
	StringBuilder.Append(DesiredExecutableVariant);
	StringBuilder.Append(ExtensionWithDot);

	return StringBuilder.ToString();
}

void UDeadlineJobPreset::SetupPluginInfo()
{
	// Set default values good for most users
	if (!JobPresetStruct.PluginInfo.FindKey("Executable"))
	{
		JobPresetStruct.PluginInfo.Add("Executable", GetExecutablePathWithDesiredVariant());
	}
	if (!JobPresetStruct.PluginInfo.FindKey("ProjectFile"))
	{
		FString ProjectPath = FPaths::GetProjectFilePath();

		if (FPaths::IsRelative(ProjectPath))
		{
			if (const FString FullPath = FPaths::ConvertRelativePathToFull(ProjectPath); FPaths::FileExists(FullPath))
			{
				ProjectPath = FullPath;
			}
		}
		
		JobPresetStruct.PluginInfo.Add("ProjectFile", ProjectPath);
	}
	if (!JobPresetStruct.PluginInfo.FindKey("CommandLineArguments"))
	{
		JobPresetStruct.PluginInfo.Add("CommandLineArguments","-log");
	}
}
