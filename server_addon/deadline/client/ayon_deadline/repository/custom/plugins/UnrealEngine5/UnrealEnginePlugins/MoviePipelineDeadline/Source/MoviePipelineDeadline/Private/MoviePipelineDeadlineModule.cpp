// Copyright Epic Games, Inc. All Rights Reserved.

#include "MoviePipelineDeadlineModule.h"

#include "DeadlineJobPreset.h"
#include "DeadlineJobPresetCustomization.h"
#include "MoviePipelineDeadlineExecutorJob.h"
#include "MoviePipelineDeadlineExecutorJobCustomization.h"

#include "Modules/ModuleManager.h"
#include "PropertyEditorModule.h"

void FMoviePipelineDeadlineModule::StartupModule()
{
	FPropertyEditorModule& PropertyModule = FModuleManager::LoadModuleChecked<FPropertyEditorModule>("PropertyEditor");

	PropertyModule.RegisterCustomClassLayout(
		UMoviePipelineDeadlineExecutorJob::StaticClass()->GetFName(),
		FOnGetDetailCustomizationInstance::CreateStatic(&FMoviePipelineDeadlineExecutorJobCustomization::MakeInstance));

	PropertyModule.RegisterCustomPropertyTypeLayout(
		FDeadlineJobPresetStruct::StaticStruct()->GetFName(),
		FOnGetPropertyTypeCustomizationInstance::CreateStatic(&FDeadlineJobPresetCustomization::MakeInstance));

	PropertyModule.NotifyCustomizationModuleChanged();
}

void FMoviePipelineDeadlineModule::ShutdownModule()
{
	if (FPropertyEditorModule* PropertyModule = FModuleManager::Get().GetModulePtr<FPropertyEditorModule>("PropertyEditor"))
	{
		PropertyModule->UnregisterCustomPropertyTypeLayout(UMoviePipelineDeadlineExecutorJob::StaticClass()->GetFName());
		PropertyModule->UnregisterCustomPropertyTypeLayout(FDeadlineJobPresetStruct::StaticStruct()->GetFName());

		PropertyModule->NotifyCustomizationModuleChanged();
	}
}

IMPLEMENT_MODULE(FMoviePipelineDeadlineModule, MoviePipelineDeadline);
