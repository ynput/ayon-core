// Copyright Epic Games, Inc. All Rights Reserved.

#include "MoviePipelineDeadlineSettings.h"

UMoviePipelineDeadlineSettings::UMoviePipelineDeadlineSettings()
{
	const TArray<FString> PropertiesToShowByDefault = {"Name", "Comment", "Department", "Pool", "Group", "Priority", "UserName"};
	
	// Set up default properties to show in MRQ
	// We do this by setting everything to hide except some defined exceptions by name
	for (TFieldIterator<FProperty> PropIt(FDeadlineJobPresetStruct::StaticStruct()); PropIt; ++PropIt)
	{
		const FProperty* Property = *PropIt;
		if (!Property)
		{
			continue;
		}

		if (PropertiesToShowByDefault.Contains(Property->GetName()))
		{
			continue;
		}
		
		JobPresetPropertiesToHideInMovieRenderQueue.Add(*Property->GetPathName());
	}
}