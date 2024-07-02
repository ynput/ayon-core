// Copyright Epic Games, Inc. All Rights Reserved.

#include "MoviePipelineDeadlineExecutorJob.h"

#include "MoviePipelineDeadlineSettings.h"

UMoviePipelineDeadlineExecutorJob::UMoviePipelineDeadlineExecutorJob()
		: UMoviePipelineExecutorJob()
{
	// If a Job Preset is not already defined, assign the default preset
	if (!JobPreset)
	{
		if (const UMoviePipelineDeadlineSettings* MpdSettings = GetDefault<UMoviePipelineDeadlineSettings>())
		{
			if (const TObjectPtr<UDeadlineJobPreset> DefaultPreset = MpdSettings->DefaultJobPreset)
			{
				JobPreset = DefaultPreset;
			}
		}
	}
}

bool UMoviePipelineDeadlineExecutorJob::IsPropertyRowEnabledInMovieRenderJob(const FName& InPropertyPath) const
{
	if (const FPropertyRowEnabledInfo* Match = Algo::FindByPredicate(EnabledPropertyOverrides,
		 [&InPropertyPath](const FPropertyRowEnabledInfo& Info)
		 {
			 return Info.PropertyPath == InPropertyPath;
		 }))
	{
		return Match->bIsEnabled;
	}

	return false;
}

void UMoviePipelineDeadlineExecutorJob::SetPropertyRowEnabledInMovieRenderJob(const FName& InPropertyPath, bool bInEnabled)
{
	if (FPropertyRowEnabledInfo* Match = Algo::FindByPredicate(EnabledPropertyOverrides,
		 [&InPropertyPath](const FPropertyRowEnabledInfo& Info)
		 {
			 return Info.PropertyPath == InPropertyPath;
		 }))
	{
		Match->bIsEnabled = bInEnabled;
	}
	else
	{
		EnabledPropertyOverrides.Add({InPropertyPath, bInEnabled});
	}
}

void UMoviePipelineDeadlineExecutorJob::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	// Check if we changed the job Preset an update the override details
	if (const FName PropertyName = PropertyChangedEvent.GetPropertyName(); PropertyName == "JobPreset")
	{
		if (const UDeadlineJobPreset* SelectedJobPreset = this->JobPreset)
		{
			this->PresetOverrides = SelectedJobPreset->JobPresetStruct;
		}
	}
}

FDeadlineJobPresetStruct UMoviePipelineDeadlineExecutorJob::GetDeadlineJobPresetStructWithOverrides() const
{
	// Start with preset properties
	FDeadlineJobPresetStruct ReturnValue = JobPreset->JobPresetStruct;
	
	const UMoviePipelineDeadlineSettings* Settings = GetDefault<UMoviePipelineDeadlineSettings>();

	for (TFieldIterator<FProperty> PropIt(FDeadlineJobPresetStruct::StaticStruct()); PropIt; ++PropIt)
	{
		const FProperty* Property = *PropIt;
		if (!Property)
		{
			continue;
		}

		const FName PropertyPath = *Property->GetPathName();

		// Skip hidden properties (just return the preset value)
		if (Settings && Settings->GetIsPropertyHiddenInMovieRenderQueue(PropertyPath))
		{
			continue;
		}

		// Also skip if it's shown but not enabled
		if (!IsPropertyRowEnabledInMovieRenderJob(PropertyPath))
		{
			continue;
		}

		// Get Override Property Value
		const void* OverridePropertyValuePtr = Property->ContainerPtrToValuePtr<void>(&PresetOverrides);

		void* ReturnPropertyValuePtr = Property->ContainerPtrToValuePtr<void>(&ReturnValue);
		Property->CopyCompleteValue(ReturnPropertyValuePtr, OverridePropertyValuePtr);
	}

	return ReturnValue;
}
